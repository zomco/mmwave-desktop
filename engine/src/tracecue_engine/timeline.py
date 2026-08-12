"""Strict timeline.v1 reader, writer and inspection helpers."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errors import TimelineValidationError, ValidationIssue
from .model import (
    Coverage,
    ExternalRef,
    Interval,
    MediaWindow,
    Producer,
    Quality,
    SourceChannel,
    SourceRef,
    TimelineDocument,
)


MAX_TIMELINE_BYTES = 8 * 1024 * 1024
_OFFSET = re.compile(r"(?:Z|[+-][0-9]{2}:[0-9]{2})$")
_EVENT_TYPE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
_CHANNEL_KINDS = {"mmwave", "door_contact", "nvr_event", "other"}
_COMPLETENESS = {"complete", "partial", "unknown"}
_GATES = {"pass", "fail", "unknown"}


@dataclass(frozen=True, slots=True)
class TimelineInspection:
    document: TimelineDocument
    content_hash: str
    size_bytes: int


def parse_rfc3339(value: Any, path: str = "timestamp") -> datetime:
    if not isinstance(value, str) or not _OFFSET.search(value):
        raise TimelineValidationError(
            [ValidationIssue(path, "TIMELINE_TIMEZONE_REQUIRED", "must include an explicit UTC offset")]
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TimelineValidationError(
            [ValidationIssue(path, "TIMELINE_TIMESTAMP_INVALID", "must be a valid RFC 3339 timestamp")]
        ) from exc
    if parsed.utcoffset() is None:
        raise TimelineValidationError(
            [ValidationIssue(path, "TIMELINE_TIMEZONE_REQUIRED", "must include an explicit UTC offset")]
        )
    return parsed


class _Validator:
    def __init__(self) -> None:
        self.issues: list[ValidationIssue] = []

    def issue(self, path: str, code: str, message: str) -> None:
        self.issues.append(ValidationIssue(path, code, message))

    def obj(
        self,
        value: Any,
        path: str,
        *,
        required: set[str],
        allowed: set[str],
    ) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            self.issue(path, "TIMELINE_TYPE_INVALID", "must be an object")
            return None
        for key in sorted(required - value.keys()):
            self.issue(f"{path}.{key}", "TIMELINE_FIELD_REQUIRED", "is required")
        for key in sorted(value.keys() - allowed):
            self.issue(f"{path}.{key}", "TIMELINE_FIELD_UNKNOWN", "is not allowed in timeline.v1")
        return value

    def text(self, value: Any, path: str, maximum: int) -> str | None:
        if not isinstance(value, str) or not value or len(value) > maximum:
            self.issue(path, "TIMELINE_TEXT_INVALID", f"must be a non-empty string of at most {maximum} characters")
            return None
        return value

    def timestamp(self, value: Any, path: str) -> datetime | None:
        try:
            return parse_rfc3339(value, path)
        except TimelineValidationError as exc:
            self.issues.extend(exc.issues)
            return None

    def number01(self, value: Any, path: str) -> float | None:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
            self.issue(path, "TIMELINE_SCORE_INVALID", "must be a number between 0 and 1")
            return None
        return float(value)

    def finish(self) -> None:
        if self.issues:
            raise TimelineValidationError(self.issues)


def _load_payload(content: bytes | str | dict[str, Any], maximum: int) -> tuple[dict[str, Any], bytes]:
    if isinstance(content, dict):
        raw = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        payload = content
    else:
        raw = content.encode("utf-8") if isinstance(content, str) else content
        if len(raw) > maximum:
            raise TimelineValidationError(
                [ValidationIssue("$", "TIMELINE_TOO_LARGE", f"document exceeds the {maximum}-byte limit")]
            )
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TimelineValidationError(
                [ValidationIssue("$", "TIMELINE_JSON_INVALID", "must be valid UTF-8 JSON")]
            ) from exc
    if len(raw) > maximum:
        raise TimelineValidationError(
            [ValidationIssue("$", "TIMELINE_TOO_LARGE", f"document exceeds the {maximum}-byte limit")]
        )
    if not isinstance(payload, dict):
        raise TimelineValidationError(
            [ValidationIssue("$", "TIMELINE_TYPE_INVALID", "document root must be an object")]
        )
    return payload, raw


def inspect_timeline(
    content: bytes | str | dict[str, Any], *, maximum_bytes: int = MAX_TIMELINE_BYTES
) -> TimelineInspection:
    payload, raw = _load_payload(content, maximum_bytes)
    document = _parse_document(payload)
    return TimelineInspection(document, hashlib.sha256(raw).hexdigest(), len(raw))


def load_timeline(path: str | Path, *, maximum_bytes: int = MAX_TIMELINE_BYTES) -> TimelineDocument:
    file_path = Path(path)
    if file_path.stat().st_size > maximum_bytes:
        raise TimelineValidationError(
            [ValidationIssue("$", "TIMELINE_TOO_LARGE", f"document exceeds the {maximum_bytes}-byte limit")]
        )
    return inspect_timeline(file_path.read_bytes(), maximum_bytes=maximum_bytes).document


def _parse_document(payload: dict[str, Any]) -> TimelineDocument:
    v = _Validator()
    required = {
        "schema_version", "document_id", "source_id", "generated_at", "producer",
        "coverage", "channels", "intervals",
    }
    root = v.obj(payload, "$", required=required, allowed=required) or {}
    if root.get("schema_version") != "timeline.v1":
        v.issue("$.schema_version", "TIMELINE_VERSION_UNSUPPORTED", "must equal timeline.v1")
    document_id = v.text(root.get("document_id"), "$.document_id", 200)
    source_id = v.text(root.get("source_id"), "$.source_id", 200)
    generated_at = v.timestamp(root.get("generated_at"), "$.generated_at")
    producer = _parse_producer(v, root.get("producer"))
    coverage = _parse_coverage(v, root.get("coverage"))
    channels = _parse_channels(v, root.get("channels"))
    intervals = _parse_intervals(v, root.get("intervals"), {item.id for item in channels})
    v.finish()
    return TimelineDocument(
        schema_version="timeline.v1",
        document_id=document_id or "",
        source_id=source_id or "",
        generated_at=generated_at or datetime.now(timezone.utc),
        producer=producer or Producer("invalid", "invalid"),
        coverage=coverage or Coverage(datetime.now(timezone.utc), datetime.now(timezone.utc), "unknown"),
        channels=tuple(channels),
        intervals=tuple(intervals),
    )


def _parse_producer(v: _Validator, value: Any) -> Producer | None:
    obj = v.obj(value, "$.producer", required={"name", "version"}, allowed={"name", "version"})
    if obj is None:
        return None
    name = v.text(obj.get("name"), "$.producer.name", 100)
    version = v.text(obj.get("version"), "$.producer.version", 100)
    return Producer(name or "", version or "")


def _parse_coverage(v: _Validator, value: Any) -> Coverage | None:
    keys = {"start_at", "end_at", "completeness"}
    obj = v.obj(value, "$.coverage", required=keys, allowed=keys)
    if obj is None:
        return None
    start = v.timestamp(obj.get("start_at"), "$.coverage.start_at")
    end = v.timestamp(obj.get("end_at"), "$.coverage.end_at")
    completeness = obj.get("completeness")
    if completeness not in _COMPLETENESS:
        v.issue("$.coverage.completeness", "TIMELINE_ENUM_INVALID", "must be complete, partial or unknown")
        completeness = "unknown"
    if start is not None and end is not None and end <= start:
        v.issue("$.coverage.end_at", "TIMELINE_RANGE_INVALID", "must be after coverage.start_at")
    return Coverage(start or datetime.now(timezone.utc), end or datetime.now(timezone.utc), completeness)


def _parse_channels(v: _Validator, value: Any) -> list[SourceChannel]:
    if not isinstance(value, list):
        v.issue("$.channels", "TIMELINE_TYPE_INVALID", "must be an array")
        return []
    result: list[SourceChannel] = []
    seen: set[str] = set()
    for index, raw in enumerate(value):
        path = f"$.channels[{index}]"
        obj = v.obj(
            raw, path, required={"id", "label", "kind"},
            allowed={"id", "label", "kind", "external_refs"},
        )
        if obj is None:
            continue
        channel_id = v.text(obj.get("id"), f"{path}.id", 200) or ""
        if channel_id in seen:
            v.issue(f"{path}.id", "TIMELINE_DUPLICATE_CHANNEL", "must be unique within the document")
        seen.add(channel_id)
        label = v.text(obj.get("label"), f"{path}.label", 200) or ""
        kind = obj.get("kind")
        if kind not in _CHANNEL_KINDS:
            v.issue(f"{path}.kind", "TIMELINE_ENUM_INVALID", "is not a supported channel kind")
            kind = "other"
        external_refs: list[ExternalRef] = []
        refs = obj.get("external_refs", [])
        if not isinstance(refs, list):
            v.issue(f"{path}.external_refs", "TIMELINE_TYPE_INVALID", "must be an array")
        else:
            for ref_index, raw_ref in enumerate(refs):
                ref_path = f"{path}.external_refs[{ref_index}]"
                ref_obj = v.obj(
                    raw_ref, ref_path, required={"namespace", "value"}, allowed={"namespace", "value"}
                )
                if ref_obj is not None:
                    namespace = v.text(ref_obj.get("namespace"), f"{ref_path}.namespace", 100)
                    ref_value = v.text(ref_obj.get("value"), f"{ref_path}.value", 500)
                    if namespace and ref_value:
                        external_refs.append(ExternalRef(namespace, ref_value))
        result.append(SourceChannel(channel_id, label, kind, tuple(external_refs)))
    return result


def _parse_intervals(v: _Validator, value: Any, channel_ids: set[str]) -> list[Interval]:
    if not isinstance(value, list):
        v.issue("$.intervals", "TIMELINE_TYPE_INVALID", "must be an array")
        return []
    result: list[Interval] = []
    seen: set[str] = set()
    required = {"id", "channel_id", "event_type", "start_at", "end_at"}
    allowed = required | {"quality", "confidence", "media_window", "tags", "source_ref", "attributes"}
    for index, raw in enumerate(value):
        path = f"$.intervals[{index}]"
        obj = v.obj(raw, path, required=required, allowed=allowed)
        if obj is None:
            continue
        interval_id = v.text(obj.get("id"), f"{path}.id", 200) or ""
        if interval_id in seen:
            v.issue(f"{path}.id", "TIMELINE_DUPLICATE_INTERVAL", "must be unique within the document")
        seen.add(interval_id)
        channel_id = v.text(obj.get("channel_id"), f"{path}.channel_id", 200) or ""
        if channel_id and channel_id not in channel_ids:
            v.issue(f"{path}.channel_id", "TIMELINE_CHANNEL_UNKNOWN", "must reference a declared channel")
        event_type = v.text(obj.get("event_type"), f"{path}.event_type", 120) or ""
        if event_type and not _EVENT_TYPE.fullmatch(event_type):
            v.issue(f"{path}.event_type", "TIMELINE_EVENT_TYPE_INVALID", "must use a dotted lowercase namespace")
        start = v.timestamp(obj.get("start_at"), f"{path}.start_at")
        end = v.timestamp(obj.get("end_at"), f"{path}.end_at")
        if start is not None and end is not None and end <= start:
            v.issue(f"{path}.end_at", "TIMELINE_RANGE_INVALID", "must be after start_at")
        quality = _parse_quality(v, obj.get("quality"), path) if "quality" in obj else None
        confidence = v.number01(obj.get("confidence"), f"{path}.confidence") if "confidence" in obj else None
        media_window = _parse_media_window(v, obj.get("media_window"), path, start, end) if "media_window" in obj else None
        tags = _parse_tags(v, obj.get("tags"), path) if "tags" in obj else ()
        source_ref = _parse_source_ref(v, obj.get("source_ref"), path) if "source_ref" in obj else None
        attributes = _parse_attributes(v, obj.get("attributes"), path) if "attributes" in obj else {}
        result.append(
            Interval(
                id=interval_id,
                channel_id=channel_id,
                event_type=event_type,
                start_at=start or datetime.now(timezone.utc),
                end_at=end or datetime.now(timezone.utc),
                quality=quality,
                confidence=confidence,
                media_window=media_window,
                tags=tags,
                source_ref=source_ref,
                attributes=attributes,
            )
        )
    return result


def _parse_quality(v: _Validator, value: Any, parent: str) -> Quality | None:
    path = f"{parent}.quality"
    obj = v.obj(value, path, required={"gate"}, allowed={"gate", "score", "reasons"})
    if obj is None:
        return None
    gate = obj.get("gate")
    if gate not in _GATES:
        v.issue(f"{path}.gate", "TIMELINE_ENUM_INVALID", "must be pass, fail or unknown")
        gate = "unknown"
    score = v.number01(obj.get("score"), f"{path}.score") if "score" in obj else None
    raw_reasons = obj.get("reasons", [])
    reasons: list[str] = []
    if not isinstance(raw_reasons, list):
        v.issue(f"{path}.reasons", "TIMELINE_TYPE_INVALID", "must be an array")
    else:
        for index, raw in enumerate(raw_reasons):
            parsed = v.text(raw, f"{path}.reasons[{index}]", 100)
            if parsed:
                reasons.append(parsed)
    return Quality(gate, score, tuple(reasons))


def _parse_media_window(
    v: _Validator, value: Any, parent: str, start: datetime | None, end: datetime | None
) -> MediaWindow | None:
    path = f"{parent}.media_window"
    obj = v.obj(value, path, required={"start_at", "end_at"}, allowed={"start_at", "end_at"})
    if obj is None:
        return None
    media_start = v.timestamp(obj.get("start_at"), f"{path}.start_at")
    media_end = v.timestamp(obj.get("end_at"), f"{path}.end_at")
    if media_start is not None and media_end is not None and media_end <= media_start:
        v.issue(f"{path}.end_at", "TIMELINE_RANGE_INVALID", "must be after media_window.start_at")
    if media_start is not None and start is not None and media_start > start:
        v.issue(f"{path}.start_at", "TIMELINE_MEDIA_WINDOW_INVALID", "must not start after the interval")
    if media_end is not None and end is not None and media_end < end:
        v.issue(f"{path}.end_at", "TIMELINE_MEDIA_WINDOW_INVALID", "must not end before the interval")
    if media_start is None or media_end is None:
        return None
    return MediaWindow(media_start, media_end)


def _parse_tags(v: _Validator, value: Any, parent: str) -> tuple[str, ...]:
    path = f"{parent}.tags"
    if not isinstance(value, list):
        v.issue(path, "TIMELINE_TYPE_INVALID", "must be an array")
        return ()
    result: list[str] = []
    for index, raw in enumerate(value):
        parsed = v.text(raw, f"{path}[{index}]", 100)
        if parsed:
            if parsed in result:
                v.issue(f"{path}[{index}]", "TIMELINE_DUPLICATE_TAG", "must be unique")
            result.append(parsed)
    return tuple(result)


def _parse_source_ref(v: _Validator, value: Any, parent: str) -> SourceRef | None:
    path = f"{parent}.source_ref"
    obj = v.obj(value, path, required=set(), allowed={"event_id", "track_id"})
    if obj is None:
        return None
    if not obj:
        v.issue(path, "TIMELINE_SOURCE_REF_EMPTY", "must contain event_id or track_id")
    event_id = v.text(obj.get("event_id"), f"{path}.event_id", 200) if "event_id" in obj else None
    track_id = v.text(obj.get("track_id"), f"{path}.track_id", 200) if "track_id" in obj else None
    return SourceRef(event_id, track_id)


def _parse_attributes(v: _Validator, value: Any, parent: str) -> dict[str, dict[str, Any]]:
    path = f"{parent}.attributes"
    if not isinstance(value, dict):
        v.issue(path, "TIMELINE_TYPE_INVALID", "must be an object")
        return {}
    result: dict[str, dict[str, Any]] = {}
    for namespace, namespace_value in value.items():
        if not isinstance(namespace, str) or not namespace:
            v.issue(path, "TIMELINE_ATTRIBUTE_NAMESPACE_INVALID", "namespace keys must be non-empty strings")
        elif not isinstance(namespace_value, dict):
            v.issue(f"{path}.{namespace}", "TIMELINE_TYPE_INVALID", "must be an object")
        else:
            result[namespace] = namespace_value
    return result


def _format_timestamp(value: datetime) -> str:
    utc = value.astimezone(timezone.utc)
    rendered = utc.isoformat(timespec="milliseconds")
    return rendered.removesuffix("+00:00") + "Z"


def _without_none(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _without_none(item) for key, item in value.items() if item is not None and item != ()}
    if isinstance(value, tuple):
        return [_without_none(item) for item in value]
    if isinstance(value, datetime):
        return _format_timestamp(value)
    return value


def dump_timeline(document: TimelineDocument, *, pretty: bool = True) -> str:
    payload = _without_none(asdict(document))
    return json.dumps(
        payload,
        ensure_ascii=False,
        indent=2 if pretty else None,
        separators=None if pretty else (",", ":"),
        sort_keys=not pretty,
    ) + ("\n" if pretty else "")

