"""Evidence-based Hikvision ISAPI adapter."""

from __future__ import annotations

import hashlib
import html
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

from .errors import AuthenticationError, PaginationError, UnsafePayloadError, UpstreamError
from .models import (
    CapabilityEvidence,
    CapabilityReport,
    ClockObservation,
    DeviceIdentity,
    MediaChannel,
    MediaResolution,
    Page,
    RecordingQuery,
    RecordingSpan,
)
from .transport import HttpResponse, Transport
from .xmlutil import children, local_name, parse_xml, text


DEVICE_INFO = "/ISAPI/System/deviceInfo"
DEVICE_TIME = "/ISAPI/System/time"
CHANNELS = "/ISAPI/System/Video/inputs/channels"
RECORD_SEARCH = "/ISAPI/ContentMgmt/search"
_OFFSET = re.compile(r"(?:Z|[+-][0-9]{2}:[0-9]{2})$")


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
        except (UpstreamError, UnsafePayloadError):
            evidence.append(self._evidence("device_time", "degraded", DEVICE_TIME, None, observed_at))

        try:
            channel_response = self.transport.request("GET", CHANNELS)
            self._parse_channels(channel_response)
            evidence.append(self._evidence("channel_discovery", "supported", CHANNELS, channel_response, observed_at))
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
        return self._parse_channels(self.transport.request("GET", CHANNELS))

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
        locators: list[str] = []
        for start, end, locator in clipped:
            if covered and start <= covered[-1][1]:
                covered[-1] = (covered[-1][0], max(covered[-1][1], end))
            else:
                covered.append((start, end))
            if locator not in locators:
                locators.append(locator)
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
            tuple(locators),
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
        return ClockObservation(observed_at, device_time, host_time, skew, timezone_text)

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
        search_id = hashlib.sha256(
            f"{query.external_channel_id}|{query.start_at.isoformat()}|{query.end_at.isoformat()}".encode()
        ).hexdigest()[:32]
        start = query.start_at.isoformat().replace("+00:00", "Z")
        end = query.end_at.isoformat().replace("+00:00", "Z")
        track_id = html.escape(query.track_id)
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<CMSearchDescription xmlns="http://www.hikvision.com/ver20/XMLSchema">'
            f"<searchID>{search_id}</searchID>"
            f"<trackList><trackID>{track_id}</trackID></trackList>"
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


def _assert_safe_locator(locator: str) -> None:
    parsed = urlsplit(locator)
    if parsed.scheme not in {"rtsp", "rtsps"} or not parsed.hostname:
        raise UnsafePayloadError("NVR returned an unsupported playback locator")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafePayloadError("credential-bearing playback locators are not accepted")
