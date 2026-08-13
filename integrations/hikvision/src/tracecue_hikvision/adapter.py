"""Evidence-based Hikvision ISAPI adapter."""

from __future__ import annotations

import hashlib
import html
import re
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .errors import AuthenticationError, PaginationError, UnsafePayloadError, UpstreamError
from .models import (
    CapabilityEvidence,
    CapabilityReport,
    ClockObservation,
    DeviceIdentity,
    EventAuditReport,
    EventRuleStatus,
    HistoricalEvent,
    HistoricalEventQuery,
    HistoricalEventResult,
    MediaChannel,
    MediaResolution,
    Page,
    RecordingQuery,
    RecordingSpan,
    ResolvedMediaSegment,
    RuleOverlay,
)
from .transport import HttpResponse, Transport
from .xmlutil import children, local_name, parse_xml, text


DEVICE_INFO = "/ISAPI/System/deviceInfo"
DEVICE_TIME = "/ISAPI/System/time"
CHANNELS = "/ISAPI/System/Video/inputs/channels"
INPUT_PROXY_CHANNEL_STATUS = "/ISAPI/ContentMgmt/InputProxy/channels/status"
RECORD_SEARCH = "/ISAPI/ContentMgmt/search"
LOG_SEARCH = "/ISAPI/ContentMgmt/logSearch"
_OFFSET = re.compile(r"(?:Z|[+-][0-9]{2}:[0-9]{2})$")
_EVENT_LOG_CLASSES = {
    "motion": ("motionStart", "motionStop"),
    "video_tamper": ("hideStart", "hideStop"),
    "line_crossing": ("lineDetectionStart", "lineDetectionStop"),
    "region_intrusion": ("fieldDetectionStart", "fieldDetectionStop"),
}
_EVENT_LOG_CLASS_LOOKUP = {
    event_class.lower(): (event_type, phase)
    for event_type, classes in _EVENT_LOG_CLASSES.items()
    for event_class, phase in zip(classes, ("start", "stop"))
}


class HikvisionAdapter:
    def __init__(self, transport: Transport, *, now=lambda: datetime.now(timezone.utc)):
        self.transport = transport
        self.now = now

    def probe(self) -> CapabilityReport:
        observed_at = self.now()
        evidence: list[CapabilityEvidence] = []
        warnings: list[dict[str, str]] = []
        try:
            device_response = self.transport.request("GET", DEVICE_INFO)
            device = self._parse_device(device_response)
            evidence.append(self._evidence("device_info", "supported", DEVICE_INFO, device_response, observed_at))
        except AuthenticationError:
            return CapabilityReport(True, False, None, None, (), ())
        except UpstreamError:
            return CapabilityReport(False, False, None, None, (), ())

        clock: ClockObservation | None = None
        try:
            time_response = self.transport.request("GET", DEVICE_TIME)
            clock = self._parse_time(time_response, observed_at)
            evidence.append(self._evidence("device_time", "supported", DEVICE_TIME, time_response, observed_at))
            if abs(clock.estimated_skew_ms) >= 30_000:
                warnings.append({"code": "CLOCK_SKEW", "message": "Device clock differs from this computer."})
        except AuthenticationError:
            evidence.append(
                self._evidence(
                    "device_time",
                    "degraded",
                    DEVICE_TIME,
                    None,
                    observed_at,
                    "endpoint denied access after device authentication",
                )
            )
            warnings.append(
                {
                    "code": "DEVICE_TIME_ACCESS_DENIED",
                    "message": "The NVR identity was authenticated, but its time endpoint denied access.",
                }
            )
        except (UpstreamError, UnsafePayloadError):
            evidence.append(self._evidence("device_time", "degraded", DEVICE_TIME, None, observed_at))

        try:
            channels, channel_endpoint, channel_response = self._discover_channels()
            evidence.append(
                self._evidence(
                    "channel_discovery",
                    "supported",
                    channel_endpoint,
                    channel_response,
                    observed_at,
                    f"discovered {len(channels)} channel(s)",
                )
            )
        except AuthenticationError:
            evidence.append(
                self._evidence(
                    "channel_discovery",
                    "degraded",
                    CHANNELS,
                    None,
                    observed_at,
                    "endpoint denied access after device authentication",
                )
            )
            warnings.append(
                {
                    "code": "CHANNEL_DISCOVERY_ACCESS_DENIED",
                    "message": "The NVR identity was authenticated, but its channel endpoint denied access.",
                }
            )
        except (UpstreamError, UnsafePayloadError):
            evidence.append(self._evidence("channel_discovery", "degraded", CHANNELS, None, observed_at))

        evidence.extend(
            (
                self._evidence("record_search", "unknown", RECORD_SEARCH, None, observed_at, "requires a bounded known window"),
                self._evidence("record_classification", "unknown", RECORD_SEARCH, None, observed_at),
                self._evidence("historical_event_search", "unknown", None, None, observed_at),
                self._evidence("realtime_event_stream", "unknown", None, None, observed_at),
                self._evidence("playback_by_uri", "unknown", RECORD_SEARCH, None, observed_at),
                self._evidence("playback_by_time", "unknown", None, None, observed_at),
            )
        )
        return CapabilityReport(True, True, device, clock, tuple(evidence), tuple(warnings))

    def list_channels(self) -> tuple[MediaChannel, ...]:
        channels, _, _ = self._discover_channels()
        return channels

    def inspect_event_settings(
        self, channels: tuple[MediaChannel, ...]
    ) -> EventAuditReport:
        """Read a bounded summary of event rules without changing device state."""
        if len(channels) > 64:
            raise ValueError("event audit is limited to 64 channels")
        rules: list[EventRuleStatus] = []
        warnings: list[dict[str, str]] = []
        for channel in channels:
            if not channel.enabled:
                continue
            track_id = channel.stream_track_ids[0] if channel.stream_track_ids else None
            probes = (
                ("motion", channel.external_id, f"/ISAPI/System/Video/inputs/channels/{channel.external_id}/motionDetection", "VMD"),
                ("video_tamper", channel.external_id, f"/ISAPI/System/Video/inputs/channels/{channel.external_id}/tamperDetection", "shelteralarm"),
                ("line_crossing", channel.external_id, f"/ISAPI/Smart/LineDetection/{channel.external_id}", "linedetection"),
                ("region_intrusion", channel.external_id, f"/ISAPI/Smart/FieldDetection/{channel.external_id}", "fielddetection"),
            )
            for event_type, identity, endpoint, trigger_type in probes:
                if not identity or not endpoint:
                    rules.append(
                        EventRuleStatus(
                            channel.external_id, track_id, event_type, "unknown", None, None,
                            None, None, None, None, "channel has no evidenced stream track identity",
                        )
                    )
                    continue
                rules.append(
                    self._inspect_event_rule(
                        channel.external_id, track_id, event_type, endpoint,
                        f"/ISAPI/Event/triggers/{trigger_type}-{identity}",
                    )
                )
        if not rules:
            warnings.append(
                {"code": "EVENT_AUDIT_NO_ONLINE_CHANNELS", "message": "No enabled channel was available for event inspection."}
            )
        return EventAuditReport(self.now(), tuple(rules), tuple(warnings))

    def search_historical_events(
        self,
        query: HistoricalEventQuery,
        *,
        maximum_pages_per_type: int = 50,
        maximum_results: int = 2_000,
    ) -> HistoricalEventResult:
        """Search bounded NVR alarm logs and return event bookmarks, not recording files."""
        if query.end_at <= query.start_at:
            raise ValueError("historical event query end must be after start")
        if not query.external_channel_ids or len(query.external_channel_ids) > 64:
            raise ValueError("historical event query requires 1 to 64 channels")
        if not 1 <= query.page_size <= 100:
            raise ValueError("page_size must be between 1 and 100")
        if maximum_pages_per_type < 1 or maximum_results < 1:
            raise ValueError("historical event pagination bounds must be positive")
        requested_types = tuple(dict.fromkeys(query.event_types or tuple(_EVENT_LOG_CLASSES)))
        unsupported = set(requested_types) - set(_EVENT_LOG_CLASSES)
        if unsupported:
            raise ValueError(f"unsupported historical event type: {sorted(unsupported)[0]}")
        selected_channels = set(query.external_channel_ids)
        probe_channel = query.external_channel_ids[0]
        if not re.fullmatch(r"[0-9A-Za-z._-]{1,64}", probe_channel):
            raise UnsafePayloadError("NVR channel identity is unsafe for event log search")
        markers: list[tuple[HistoricalEvent, str]] = []
        seen: set[str] = set()
        truncated = False
        for event_type in requested_types:
            for event_class in _EVENT_LOG_CLASSES[event_type]:
                phase = "start" if event_class.lower().endswith("start") else "stop"
                position = 0
                for _ in range(maximum_pages_per_type):
                    body = self._event_log_search_body(
                        query, event_class, probe_channel, position, include_stop_lookahead=phase == "stop"
                    )
                    response = self.transport.request(
                        "POST",
                        LOG_SEARCH,
                        body=body,
                        headers={"Content-Type": "application/xml; charset=utf-8"},
                    )
                    root = parse_xml(response.body)
                    status = " ".join((text(root, "responseStatusStrg") or "").upper().split())
                    matches = children(root, "searchMatchItem")
                    for item in matches:
                        parsed = self._parse_historical_event(item, selected_channels)
                        if parsed is None:
                            continue
                        event, parsed_phase = parsed
                        upper_bound = query.end_at + (timedelta(hours=1) if parsed_phase == "stop" else timedelta())
                        if (
                            event.event_type != event_type
                            or event.occurred_at < query.start_at
                            or event.occurred_at >= upper_bound
                            or event.source_id in seen
                        ):
                            continue
                        seen.add(event.source_id)
                        markers.append((event, parsed_phase))
                    if "MORE" not in status:
                        break
                    if not matches:
                        raise PaginationError("NVR event log search did not advance")
                    position += len(matches)
                else:
                    truncated = True

        pending: dict[tuple[str, str], list[HistoricalEvent]] = {}
        paired: list[HistoricalEvent] = []
        for marker, phase in sorted(markers, key=lambda value: value[0].occurred_at):
            key = (marker.external_channel_id, marker.event_type)
            if phase == "start":
                if marker.occurred_at < query.end_at:
                    pending.setdefault(key, []).append(marker)
                continue
            starts = pending.get(key, [])
            while starts and marker.occurred_at - starts[0].occurred_at > timedelta(hours=1):
                paired.append(starts.pop(0))
            if starts and marker.occurred_at > starts[0].occurred_at:
                start = starts.pop(0)
                paired.append(
                    HistoricalEvent(
                        start.external_channel_id,
                        start.event_type,
                        start.occurred_at,
                        start.classification,
                        start.source_id,
                        marker.occurred_at,
                    )
                )
        for starts in pending.values():
            paired.extend(starts)
        paired.sort(key=lambda event: event.occurred_at)
        if len(paired) > maximum_results:
            return HistoricalEventResult(tuple(paired[:maximum_results]), True)
        return HistoricalEventResult(tuple(paired), truncated)

    @staticmethod
    def _parse_historical_event(
        item, selected_channels: set[str]
    ) -> tuple[HistoricalEvent, str] | None:
        classification = text(item, "metaId")
        occurred = text(item, "StartDateTime") or text(item, "startTime")
        if not classification or not occurred or len(classification) > 256:
            return None
        match = re.fullmatch(
            r"log\.hikvision\.com/Alarm/([A-Za-z]+)/([0-9A-Za-z._-]{1,64})",
            classification,
            re.IGNORECASE,
        )
        if not match:
            return None
        event_identity = _EVENT_LOG_CLASS_LOOKUP.get(match.group(1).lower())
        channel_external_id = match.group(2)
        if event_identity is None or channel_external_id not in selected_channels:
            return None
        event_type, phase = event_identity
        occurred_at = _parse_time(occurred)
        source_id = hashlib.sha256(
            f"{classification.lower()}|{occurred_at.isoformat()}".encode("utf-8")
        ).hexdigest()[:32]
        return (
            HistoricalEvent(
                channel_external_id,
                event_type,
                occurred_at,
                classification,
                source_id,
            ),
            phase,
        )

    @staticmethod
    def _event_log_search_body(
        query: HistoricalEventQuery,
        event_class: str,
        probe_channel: str,
        position: int,
        *,
        include_stop_lookahead: bool = False,
    ) -> bytes:
        search_id = uuid.uuid5(
            uuid.NAMESPACE_URL,
            "tracecue:event-log-search:"
            f"{event_class}|{query.start_at.isoformat()}|{query.end_at.isoformat()}|"
            f"{'|'.join(query.external_channel_ids)}",
        )
        start = query.start_at.isoformat().replace("+00:00", "Z")
        end_at = query.end_at + (timedelta(hours=1) if include_stop_lookahead else timedelta())
        end = end_at.isoformat().replace("+00:00", "Z")
        meta_id = html.escape(f"log.hikvision.com/Alarm/{event_class}/{probe_channel}")
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<CMSearchDescription version="1.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">'
            f"<searchID>{search_id}</searchID>"
            f"<timeSpanList><timeSpan><startTime>{start}</startTime><endTime>{end}</endTime></timeSpan></timeSpanList>"
            f"<metaId>{meta_id}</metaId>"
            f"<searchResultPostion>{position}</searchResultPostion>"
            f"<maxResults>{query.page_size}</maxResults>"
            "</CMSearchDescription>"
        ).encode("utf-8")

    def _inspect_event_rule(
        self,
        channel_external_id: str,
        track_id: str | None,
        event_type: str,
        endpoint: str,
        trigger_endpoint: str,
    ) -> EventRuleStatus:
        try:
            response = self.transport.request("GET", endpoint, maximum_bytes=512 * 1024)
        except AuthenticationError:
            return EventRuleStatus(
                channel_external_id, track_id, event_type, "degraded", None, None,
                None, None, None, endpoint, "event rule endpoint denied access",
            )
        except UpstreamError:
            return EventRuleStatus(
                channel_external_id, track_id, event_type, "unknown", None, None,
                None, None, None, endpoint, "event rule endpoint unavailable on this model/firmware",
            )
        root = parse_xml(response.body)
        enabled = _parse_bool(text(root, "enabled"))
        sensitivity = _parse_int(text(root, "sensitivityLevel") or text(root, "sensitivity"), 0, 100)
        overlays = _parse_rule_overlays(root, event_type)
        region_names = {"Region", "DetectionRegion", "FieldDetectionRegion", "LineDetectionRegion"}
        region_count = len(overlays) or sum(1 for item in root.iter() if local_name(item.tag) in region_names)
        schedule_names = {"TimeBlock", "TimeSegment", "ScheduleAction"}
        schedule_block_count = sum(1 for item in root.iter() if local_name(item.tag) in schedule_names)
        notification_configured: bool | None = None
        note = None
        try:
            trigger = self.transport.request("GET", trigger_endpoint, maximum_bytes=512 * 1024)
            trigger_root = parse_xml(trigger.body)
            notification_configured = any(
                local_name(item.tag) in {"EventTriggerNotification", "notificationMethod"}
                and (item.text or list(item))
                for item in trigger_root.iter()
            )
        except AuthenticationError:
            note = "event rule readable; linkage/notification endpoint denied access"
        except UpstreamError:
            note = "event rule readable; linkage/notification state unavailable"
        return EventRuleStatus(
            channel_external_id, track_id, event_type, "supported", enabled,
            notification_configured, sensitivity, region_count, schedule_block_count,
            endpoint, note, overlays,
        )

    def search_recordings(self, query: RecordingQuery) -> Page:
        if query.end_at <= query.start_at:
            raise ValueError("recording query end must be after start")
        if not 1 <= query.page_size <= 100:
            raise ValueError("page_size must be between 1 and 100")
        body = self._search_body(query)
        response = self.transport.request(
            "POST",
            RECORD_SEARCH,
            body=body,
            headers={"Content-Type": "application/xml; charset=utf-8"},
        )
        return self._parse_recordings(response, query)

    def search_all_recordings(
        self,
        query: RecordingQuery,
        *,
        maximum_pages: int = 50,
        maximum_results: int = 2_000,
    ) -> tuple[RecordingSpan, ...]:
        if maximum_pages < 1 or maximum_results < 1:
            raise ValueError("pagination bounds must be positive")
        current = query
        seen_positions: set[int] = set()
        result: list[RecordingSpan] = []
        for _ in range(maximum_pages):
            if current.position in seen_positions:
                raise PaginationError("NVR recording search did not advance")
            seen_positions.add(current.position)
            page = self.search_recordings(current)
            result.extend(page.items)
            if len(result) > maximum_results:
                raise PaginationError("NVR recording search exceeded the result limit")
            if page.complete:
                return tuple(result)
            if page.next_position is None or page.next_position <= current.position:
                raise PaginationError("NVR recording search returned a non-progressing position")
            current = RecordingQuery(
                external_channel_id=query.external_channel_id,
                track_id=query.track_id,
                start_at=query.start_at,
                end_at=query.end_at,
                position=page.next_position,
                page_size=query.page_size,
            )
        raise PaginationError("NVR recording search exceeded the page limit")

    @staticmethod
    def resolve_media(
        spans: tuple[RecordingSpan, ...], requested_start: datetime, requested_end: datetime
    ) -> MediaResolution:
        if requested_end <= requested_start:
            raise ValueError("requested media end must be after start")
        clipped: list[tuple[datetime, datetime, str]] = []
        for span in sorted(spans, key=lambda item: item.start_at):
            start = max(span.start_at, requested_start)
            end = min(span.end_at, requested_end)
            if end > start:
                clipped.append((start, end, span.playback_locator))
        covered: list[tuple[datetime, datetime]] = []
        segments: list[ResolvedMediaSegment] = []
        for start, end, locator in clipped:
            if covered and start <= covered[-1][1]:
                covered[-1] = (covered[-1][0], max(covered[-1][1], end))
            else:
                covered.append((start, end))
            if not any(segment.playback_locator == locator for segment in segments):
                segments.append(ResolvedMediaSegment(start, end, locator))
        missing: list[tuple[datetime, datetime]] = []
        cursor = requested_start
        for start, end in covered:
            if start > cursor:
                missing.append((cursor, start))
            cursor = max(cursor, end)
        if cursor < requested_end:
            missing.append((cursor, requested_end))
        return MediaResolution(
            requested_start,
            requested_end,
            tuple(covered),
            tuple(missing),
            tuple(segments),
        )

    def _parse_device(self, response: HttpResponse) -> DeviceIdentity:
        root = parse_xml(response.body)
        return DeviceIdentity(text(root, "model"), text(root, "firmwareVersion"), text(root, "serialNumber"))

    def _parse_time(self, response: HttpResponse, observed_at: datetime) -> ClockObservation:
        root = parse_xml(response.body)
        local_time = text(root, "localTime")
        timezone_text = text(root, "timeZone") or "unknown"
        device_time = _parse_time(local_time)
        host_time = self.now()
        skew = int((device_time.astimezone(timezone.utc) - host_time.astimezone(timezone.utc)).total_seconds() * 1000)
        offset = device_time.utcoffset() or timedelta(0)
        return ClockObservation(
            observed_at,
            device_time,
            host_time,
            skew,
            timezone_text,
            int(offset.total_seconds() // 60),
        )

    def _parse_channels(self, response: HttpResponse) -> tuple[MediaChannel, ...]:
        root = parse_xml(response.body)
        result: list[MediaChannel] = []
        for item in children(root, "VideoInputChannel"):
            external_id = text(item, "id")
            if not external_id:
                continue
            name = text(item, "name") or f"Channel {external_id}"
            enabled = (text(item, "enabled") or "true").lower() == "true"
            input_port_text = text(item, "inputPort")
            input_port = int(input_port_text) if input_port_text and input_port_text.isdigit() else None
            tracks = tuple(
                node.text.strip()
                for node in item.iter()
                if local_name(node.tag) in {"streamingChannelID", "trackID"} and node.text
            )
            result.append(MediaChannel(external_id, name, enabled, input_port, tuple(dict.fromkeys(tracks))))
        return tuple(result)

    def _discover_channels(
        self,
    ) -> tuple[tuple[MediaChannel, ...], str, HttpResponse]:
        last_error: AuthenticationError | UpstreamError | None = None
        for endpoint, parser in (
            (CHANNELS, self._parse_channels),
            (INPUT_PROXY_CHANNEL_STATUS, self._parse_input_proxy_channel_status),
        ):
            try:
                response = self.transport.request("GET", endpoint)
                return parser(response), endpoint, response
            except (AuthenticationError, UpstreamError) as exc:
                last_error = exc
        assert last_error is not None
        raise last_error

    def _parse_input_proxy_channel_status(
        self, response: HttpResponse
    ) -> tuple[MediaChannel, ...]:
        root = parse_xml(response.body)
        result: list[MediaChannel] = []
        for item in children(root, "InputProxyChannelStatus"):
            external_id = text(item, "id")
            if not external_id:
                continue
            name = text(item, "name") or f"Channel {external_id}"
            online = (text(item, "online") or "false").lower() == "true"
            input_port_text = text(item, "srcInputPort")
            input_port = (
                int(input_port_text)
                if input_port_text and input_port_text.isdigit()
                else None
            )
            tracks = tuple(
                node.text.strip()
                for node in item.iter()
                if local_name(node.tag) == "streamingProxyChannelId" and node.text
            )
            result.append(
                MediaChannel(
                    external_id,
                    name,
                    online,
                    input_port,
                    tuple(dict.fromkeys(tracks)),
                )
            )
        return tuple(result)

    def _parse_recordings(self, response: HttpResponse, query: RecordingQuery) -> Page:
        root = parse_xml(response.body)
        status = " ".join((text(root, "responseStatusStrg") or "").lower().split())
        items: list[RecordingSpan] = []
        for item in children(root, "searchMatchItem"):
            time_spans = children(item, "timeSpan")
            if not time_spans:
                continue
            start = _parse_time(text(time_spans[0], "startTime"))
            end = _parse_time(text(time_spans[0], "endTime"))
            if end <= start:
                continue
            locator = text(item, "playbackURI")
            if not locator:
                continue
            _assert_safe_locator(locator)
            locator = _normalize_playback_locator(locator)
            classification = text(item, "metadataDescriptor") or "unknown"
            source_id = text(item, "fileName") or text(item, "searchID")
            items.append(RecordingSpan(start, end, classification, locator, source_id))
        reported_matches = text(root, "numOfMatches")
        count = int(reported_matches) if reported_matches and reported_matches.isdigit() else len(items)
        has_more = "more" in status and "match" in status and "no more" not in status
        explicitly_complete = status in {"ok", "nomorematch", "no more matches", "nomatch", "no match"}
        complete = explicitly_complete or (not has_more and count < query.page_size)
        next_position = None if complete else query.position + count
        return Page(tuple(items), next_position, complete)

    @staticmethod
    def _evidence(
        capability: str,
        state: str,
        endpoint: str | None,
        response: HttpResponse | None,
        observed_at: datetime,
        note: str | None = None,
    ) -> CapabilityEvidence:
        return CapabilityEvidence(
            capability,
            state,
            endpoint,
            response.status_code if response else None,
            hashlib.sha256(response.body).hexdigest() if response else None,
            observed_at,
            note,
        )

    @staticmethod
    def _search_body(query: RecordingQuery) -> bytes:
        search_id = uuid.uuid5(
            uuid.NAMESPACE_URL,
            "tracecue:recording-search:"
            f"{query.external_channel_id}|{query.start_at.isoformat()}|{query.end_at.isoformat()}",
        )
        start = query.start_at.isoformat().replace("+00:00", "Z")
        end = query.end_at.isoformat().replace("+00:00", "Z")
        track_id = html.escape(query.track_id)
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<CMSearchDescription xmlns="http://www.hikvision.com/ver20/XMLSchema">'
            f"<searchID>{search_id}</searchID>"
            f"<trackIDList><trackID>{track_id}</trackID></trackIDList>"
            f"<timeSpanList><timeSpan><startTime>{start}</startTime><endTime>{end}</endTime></timeSpan></timeSpanList>"
            f"<maxResults>{query.page_size}</maxResults>"
            f"<searchResultPostion>{query.position}</searchResultPostion>"
            '<metadataList><metadataDescriptor>//recordType.meta.std-cgi.com</metadataDescriptor></metadataList>'
            "</CMSearchDescription>"
        ).encode("utf-8")


def _parse_time(value: str | None) -> datetime:
    if not value or not _OFFSET.search(value):
        raise UnsafePayloadError("NVR timestamp is missing an explicit UTC offset")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise UnsafePayloadError("NVR returned an invalid timestamp") from exc


def _parse_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    return None


def _parse_int(value: str | None, minimum: int, maximum: int) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if minimum <= parsed <= maximum else None


def _assert_safe_locator(locator: str) -> None:
    parsed = urlsplit(locator)
    if parsed.scheme not in {"rtsp", "rtsps"} or not parsed.hostname:
        raise UnsafePayloadError("NVR returned an unsupported playback locator")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafePayloadError("credential-bearing playback locators are not accepted")


def _normalize_playback_locator(locator: str) -> str:
    """Repair firmware that publishes RTSP locators on its HTTP service port."""
    parsed = urlsplit(locator)
    if parsed.scheme != "rtsp" or parsed.port not in {80, 443}:
        return locator
    host = parsed.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return urlunsplit((parsed.scheme, f"{host}:554", parsed.path, parsed.query, parsed.fragment))


def playback_locator_for_device_time(locator: str, utc_offset_minutes: int) -> str:
    """Translate UTC locator tokens to Hikvision's device-local RTSP wall time."""
    if not utc_offset_minutes:
        return locator
    parsed = urlsplit(locator)
    translated: list[tuple[str, str]] = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if key.lower() not in {"starttime", "endtime"}:
            translated.append((key, value))
            continue
        match = re.fullmatch(r"([0-9]{8})T([0-9]{6})Z", value, re.IGNORECASE)
        if not match:
            translated.append((key, value))
            continue
        instant = datetime.strptime("".join(match.groups()), "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        wall_clock = instant + timedelta(minutes=utc_offset_minutes)
        translated.append((key, wall_clock.strftime("%Y%m%dT%H%M%SZ")))
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(translated), parsed.fragment))


def playback_locator_for_window(
    locator: str, start_at: datetime, end_at: datetime
) -> str:
    """Replace a broad NVR locator's bounds with the resolved UTC media segment."""
    if end_at <= start_at:
        raise ValueError("playback locator end must be after start")
    parsed = urlsplit(locator)
    bounded = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in {"starttime", "endtime"}
    ]
    bounded.extend(
        (
            ("starttime", start_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")),
            ("endtime", end_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")),
        )
    )
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(bounded), parsed.fragment))


def _parse_rule_overlays(root, event_type: str) -> tuple[RuleOverlay, ...]:
    overlays: list[RuleOverlay] = []
    rows = _parse_int(text(root, "rowGranularity"), 1, 128)
    columns = _parse_int(text(root, "columnGranularity"), 1, 128)
    grid_map = (text(root, "gridMap") or "").strip()
    if rows and columns and grid_map and len(grid_map) <= 16_384 and re.fullmatch(r"[0-9a-fA-F]+", grid_map):
        row_width = (columns + 3) // 4
        if len(grid_map) >= rows * row_width:
            cells: list[tuple[int, int]] = []
            for row in range(rows):
                bits = bin(int(grid_map[row * row_width:(row + 1) * row_width], 16))[2:].zfill(row_width * 4)
                cells.extend((column, row) for column, bit in enumerate(bits[:columns]) if bit == "1")
            if cells:
                overlays.append(RuleOverlay("grid", columns, rows, active_cells=tuple(cells)))

    coordinate_containers = {
        "RegionCoordinatesList", "CoordinatesList", "PointList",
        "LineCoordinatesList", "PolygonCoordinatesList",
    }
    seen: set[tuple[tuple[int, int], ...]] = set()
    for container in root.iter():
        if local_name(container.tag) not in coordinate_containers:
            continue
        x_values = [
            _parse_int((item.text or "").strip(), 0, 1_000_000)
            for item in container.iter() if local_name(item.tag) in {"positionX", "x"}
        ]
        y_values = [
            _parse_int((item.text or "").strip(), 0, 1_000_000)
            for item in container.iter() if local_name(item.tag) in {"positionY", "y"}
        ]
        points = tuple(
            (x, y) for x, y in zip(x_values[:128], y_values[:128])
            if x is not None and y is not None
        )
        # Evidenced Hikvision Smart coordinate-list endpoints use the lower image
        # edge as the vertical origin. Normalize them to TraceCue's top-left SVG
        # coordinate system. Motion grids already use row order and are unchanged.
        if event_type in {"line_crossing", "region_intrusion"}:
            points = tuple((x, 1_000 - y) for x, y in points)
        if len(points) < 2 or points in seen:
            continue
        kind = "line" if event_type == "line_crossing" or len(points) == 2 else "polygon"
        unique_points = set(points)
        if kind == "line" and len(unique_points) < 2:
            continue
        if kind == "polygon":
            if len(unique_points) < 3:
                continue
            twice_area = abs(sum(
                first[0] * second[1] - second[0] * first[1]
                for first, second in zip(points, points[1:] + points[:1])
            ))
            if twice_area == 0:
                continue
        seen.add(points)
        width = max(1_000, max(point[0] for point in points))
        height = max(1_000, max(point[1] for point in points))
        overlays.append(RuleOverlay(kind, width, height, points=points))
        if len(overlays) >= 64:
            break
    return tuple(overlays)
