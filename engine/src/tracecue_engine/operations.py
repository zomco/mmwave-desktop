"""Deterministic interval operations shared by gateway and desktop."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Iterable, Literal

from .model import Interval, MediaWindow, Quality


@dataclass(frozen=True, slots=True)
class QualityGateResult:
    gate: Literal["pass", "fail", "unknown"]
    score: float | None
    reasons: tuple[str, ...]


def utc_millis(value: datetime) -> int:
    if value.utcoffset() is None:
        raise ValueError("timestamp must include an explicit UTC offset")
    return int(value.timestamp() * 1000)


def from_utc_millis(value: int) -> datetime:
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc)


def deterministic_interval_id(
    source_id: str,
    channel_id: str,
    event_type: str,
    start_at: datetime,
    end_at: datetime,
    *,
    source_identity: str = "",
) -> str:
    if not source_id or not channel_id or not event_type:
        raise ValueError("source, channel and event type must be non-empty")
    if end_at <= start_at:
        raise ValueError("end_at must be after start_at")
    identity = "\x1f".join(
        (source_id, channel_id, event_type, str(utc_millis(start_at)), str(utc_millis(end_at)), source_identity)
    )
    return "int_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]


def evaluate_quality(
    score: float | None,
    *,
    minimum_score: float,
    required_observations_present: bool = True,
    clock_healthy: bool = True,
    reasons: Iterable[str] = (),
) -> QualityGateResult:
    if not 0 <= minimum_score <= 1:
        raise ValueError("minimum_score must be between 0 and 1")
    collected = list(reasons)
    if not required_observations_present:
        collected.append("missing_required_observations")
    if not clock_healthy:
        collected.append("clock_unhealthy")
    if score is None:
        collected.append("score_unknown")
        gate = "unknown" if required_observations_present and clock_healthy else "fail"
    elif not 0 <= score <= 1:
        raise ValueError("score must be between 0 and 1")
    elif score < minimum_score:
        collected.append("score_below_threshold")
        gate = "fail"
    elif required_observations_present and clock_healthy:
        gate = "pass"
    else:
        gate = "fail"
    return QualityGateResult(gate, score, tuple(dict.fromkeys(collected)))


def calculate_media_window(interval: Interval, *, pre_roll_ms: int, post_roll_ms: int) -> MediaWindow:
    if pre_roll_ms < 0 or post_roll_ms < 0:
        raise ValueError("roll values must not be negative")
    return MediaWindow(
        interval.start_at - timedelta(milliseconds=pre_roll_ms),
        interval.end_at + timedelta(milliseconds=post_roll_ms),
    )


def filter_intervals(
    intervals: Iterable[Interval],
    *,
    channel_ids: set[str] | None = None,
    event_types: set[str] | None = None,
    quality_gates: set[str] | None = None,
    minimum_confidence: float | None = None,
) -> tuple[Interval, ...]:
    if minimum_confidence is not None and not 0 <= minimum_confidence <= 1:
        raise ValueError("minimum_confidence must be between 0 and 1")
    result = []
    for interval in intervals:
        if channel_ids is not None and interval.channel_id not in channel_ids:
            continue
        if event_types is not None and interval.event_type not in event_types:
            continue
        gate = interval.quality.gate if interval.quality else "unknown"
        if quality_gates is not None and gate not in quality_gates:
            continue
        if minimum_confidence is not None and (
            interval.confidence is None or interval.confidence < minimum_confidence
        ):
            continue
        result.append(interval)
    return tuple(result)


def upsert_by_identity(
    existing: dict[tuple[str, str], Interval],
    source_id: str,
    incoming: Iterable[Interval],
) -> tuple[dict[tuple[str, str], Interval], int, int]:
    merged = dict(existing)
    inserted = 0
    updated = 0
    for interval in incoming:
        key = (source_id, interval.id)
        if key in merged:
            if merged[key] != interval:
                updated += 1
        else:
            inserted += 1
        merged[key] = interval
    return merged, inserted, updated


def merge_intervals(intervals: Iterable[Interval], *, maximum_gap_ms: int = 0) -> tuple[Interval, ...]:
    if maximum_gap_ms < 0:
        raise ValueError("maximum_gap_ms must not be negative")
    ordered = sorted(intervals, key=lambda item: (item.channel_id, item.event_type, item.start_at, item.id))
    if not ordered:
        return ()
    result: list[Interval] = []
    group: list[Interval] = []
    for interval in ordered:
        if not group:
            group = [interval]
            continue
        previous = group[-1]
        compatible = previous.channel_id == interval.channel_id and previous.event_type == interval.event_type
        gap_ms = utc_millis(interval.start_at) - utc_millis(previous.end_at)
        if compatible and gap_ms <= maximum_gap_ms:
            group.append(interval)
        else:
            result.append(_merge_group(group))
            group = [interval]
    result.append(_merge_group(group))
    return tuple(result)


def _merge_group(group: list[Interval]) -> Interval:
    if len(group) == 1:
        return group[0]
    first = group[0]
    start = min(item.start_at for item in group)
    end = max(item.end_at for item in group)
    media_starts = [item.media_window.start_at for item in group if item.media_window]
    media_ends = [item.media_window.end_at for item in group if item.media_window]
    gates = [item.quality.gate for item in group if item.quality]
    scores = [item.quality.score for item in group if item.quality and item.quality.score is not None]
    reasons = tuple(
        dict.fromkeys(reason for item in group if item.quality for reason in item.quality.reasons)
    )
    if "fail" in gates:
        gate = "fail"
    elif gates and all(item == "pass" for item in gates):
        gate = "pass"
    else:
        gate = "unknown"
    quality = Quality(gate, min(scores) if scores else None, reasons) if gates else None
    confidence_values = [item.confidence for item in group if item.confidence is not None]
    component_ids = sorted(item.id for item in group)
    merged_attributes = dict(first.attributes)
    merged_attributes["tracecue_engine"] = {"merged_interval_ids": component_ids}
    merged_id = deterministic_interval_id(
        "merged", first.channel_id, first.event_type, start, end, source_identity="|".join(component_ids)
    )
    return replace(
        first,
        id=merged_id,
        start_at=start,
        end_at=end,
        quality=quality,
        confidence=min(confidence_values) if confidence_values else None,
        media_window=MediaWindow(min(media_starts), max(media_ends)) if media_starts and media_ends else None,
        tags=tuple(sorted({tag for item in group for tag in item.tags})),
        source_ref=None,
        attributes=merged_attributes,
    )

