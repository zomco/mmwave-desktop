"""Immutable, vendor-neutral timeline value types."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


ChannelKind = Literal["mmwave", "door_contact", "nvr_event", "other"]
Completeness = Literal["complete", "partial", "unknown"]
Gate = Literal["pass", "fail", "unknown"]


@dataclass(frozen=True, slots=True)
class Producer:
    name: str
    version: str


@dataclass(frozen=True, slots=True)
class Coverage:
    start_at: datetime
    end_at: datetime
    completeness: Completeness


@dataclass(frozen=True, slots=True)
class ExternalRef:
    namespace: str
    value: str


@dataclass(frozen=True, slots=True)
class SourceChannel:
    id: str
    label: str
    kind: ChannelKind
    external_refs: tuple[ExternalRef, ...] = ()


@dataclass(frozen=True, slots=True)
class Quality:
    gate: Gate
    score: float | None = None
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MediaWindow:
    start_at: datetime
    end_at: datetime


@dataclass(frozen=True, slots=True)
class SourceRef:
    event_id: str | None = None
    track_id: str | None = None


@dataclass(frozen=True, slots=True)
class Interval:
    id: str
    channel_id: str
    event_type: str
    start_at: datetime
    end_at: datetime
    quality: Quality | None = None
    confidence: float | None = None
    media_window: MediaWindow | None = None
    tags: tuple[str, ...] = ()
    source_ref: SourceRef | None = None
    attributes: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TimelineDocument:
    schema_version: Literal["timeline.v1"]
    document_id: str
    source_id: str
    generated_at: datetime
    producer: Producer
    coverage: Coverage
    channels: tuple[SourceChannel, ...]
    intervals: tuple[Interval, ...]

