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
class NvrDeviceDetails:
    device_name: str | None
    device_type: str | None
    model: str | None
    firmware: str | None
    serial_number: str | None = field(default=None, repr=False)
    mac_address: str | None = None
    device_id: str | None = None
    firmware_released_date: str | None = None
    encoder_version: str | None = None
    encoder_released_date: str | None = None


@dataclass(frozen=True, slots=True)
class CameraDeviceDetails:
    external_channel_id: str
    name: str | None
    online: bool | None
    model: str | None = None
    firmware: str | None = None
    serial_number: str | None = field(default=None, repr=False)
    device_id: str | None = None
    protocol: str | None = None
    address: str | None = None
    manage_port: int | None = None
    source_input_port: int | None = None
    stream_type: str | None = None


@dataclass(frozen=True, slots=True)
class DeviceDetailsReport:
    observed_at: datetime
    nvr: NvrDeviceDetails
    cameras: tuple[CameraDeviceDetails, ...]
    warnings: tuple[dict[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class ClockObservation:
    observed_at: datetime
    device_time: datetime
    host_time: datetime
    estimated_skew_ms: int
    timezone: str
    utc_offset_minutes: int = 0


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
class HistoricalEventQuery:
    external_channel_ids: tuple[str, ...]
    event_types: tuple[str, ...]
    start_at: datetime
    end_at: datetime
    page_size: int = 100


@dataclass(frozen=True, slots=True)
class HistoricalEvent:
    external_channel_id: str
    event_type: str
    occurred_at: datetime
    classification: str
    source_id: str
    ended_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class HistoricalEventResult:
    items: tuple[HistoricalEvent, ...]
    truncated: bool = False


@dataclass(frozen=True, slots=True)
class Page:
    items: tuple[RecordingSpan, ...]
    next_position: int | None
    complete: bool


@dataclass(frozen=True, slots=True)
class ResolvedMediaSegment:
    start_at: datetime
    end_at: datetime
    playback_locator: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class MediaResolution:
    requested_start_at: datetime
    requested_end_at: datetime
    covered_spans: tuple[tuple[datetime, datetime], ...]
    missing_spans: tuple[tuple[datetime, datetime], ...]
    playback_segments: tuple[ResolvedMediaSegment, ...] = field(repr=False)

    @property
    def playback_locators(self) -> tuple[str, ...]:
        return tuple(segment.playback_locator for segment in self.playback_segments)

    @property
    def complete(self) -> bool:
        return not self.missing_spans


@dataclass(frozen=True, slots=True)
class DiscoveredDevice:
    host: str
    http_port: int
    use_https: bool
    name: str
    model: str | None
    device_types: tuple[str, ...]
    discovery_protocol: str = "onvif_ws_discovery"


@dataclass(frozen=True, slots=True)
class RuleOverlay:
    kind: Literal["grid", "polygon", "line"]
    width: int
    height: int
    points: tuple[tuple[int, int], ...] = ()
    active_cells: tuple[tuple[int, int], ...] = ()


@dataclass(frozen=True, slots=True)
class EventRuleStatus:
    channel_external_id: str
    track_id: str | None
    event_type: str
    state: CapabilityState
    enabled: bool | None
    notification_configured: bool | None
    sensitivity: int | None
    region_count: int | None
    schedule_block_count: int | None
    endpoint: str | None
    note: str | None = None
    overlays: tuple[RuleOverlay, ...] = ()


@dataclass(frozen=True, slots=True)
class EventAuditReport:
    observed_at: datetime
    rules: tuple[EventRuleStatus, ...]
    warnings: tuple[dict[str, str], ...] = ()
