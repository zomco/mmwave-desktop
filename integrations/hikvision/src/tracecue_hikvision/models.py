"""Typed adapter boundary independent from desktop persistence."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


CapabilityState = Literal["supported", "unsupported", "unknown", "degraded"]


@dataclass(frozen=True, slots=True)
class ConnectionConfig:
    host: str
    username: str
    password: str = field(repr=False)
    http_port: int = 80
    use_https: bool = False
    verify_tls: bool = True
    timeout_seconds: float = 10.0

    @property
    def base_url(self) -> str:
        scheme = "https" if self.use_https else "http"
        return f"{scheme}://{self.host}:{self.http_port}"


@dataclass(frozen=True, slots=True)
class DeviceIdentity:
    model: str | None
    firmware: str | None
    serial_number: str | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class ClockObservation:
    observed_at: datetime
    device_time: datetime
    host_time: datetime
    estimated_skew_ms: int
    timezone: str


@dataclass(frozen=True, slots=True)
class CapabilityEvidence:
    capability: str
    state: CapabilityState
    endpoint: str | None
    status_code: int | None
    fixture_hash: str | None
    observed_at: datetime
    note: str | None = None


@dataclass(frozen=True, slots=True)
class CapabilityReport:
    reachable: bool
    authenticated: bool
    device: DeviceIdentity | None
    clock: ClockObservation | None
    capabilities: tuple[CapabilityEvidence, ...]
    warnings: tuple[dict[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class MediaChannel:
    external_id: str
    name: str
    enabled: bool
    input_port: int | None = None
    stream_track_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RecordingQuery:
    external_channel_id: str
    track_id: str
    start_at: datetime
    end_at: datetime
    position: int = 0
    page_size: int = 40


@dataclass(frozen=True, slots=True)
class RecordingSpan:
    start_at: datetime
    end_at: datetime
    classification: str
    playback_locator: str = field(repr=False)
    source_id: str | None = None


@dataclass(frozen=True, slots=True)
class Page:
    items: tuple[RecordingSpan, ...]
    next_position: int | None
    complete: bool


@dataclass(frozen=True, slots=True)
class MediaResolution:
    requested_start_at: datetime
    requested_end_at: datetime
    covered_spans: tuple[tuple[datetime, datetime], ...]
    missing_spans: tuple[tuple[datetime, datetime], ...]
    playback_locators: tuple[str, ...] = field(repr=False)

    @property
    def complete(self) -> bool:
        return not self.missing_spans

