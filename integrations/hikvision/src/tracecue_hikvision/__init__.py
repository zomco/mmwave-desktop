"""Public Hikvision adapter API."""

from .adapter import HikvisionAdapter
from .discovery import discover_devices, parse_discovery_response
from .errors import (
    AuthenticationError,
    HikvisionError,
    PaginationError,
    ResponseLimitError,
    UnsafePayloadError,
    UpstreamError,
)
from .models import (
    CapabilityEvidence,
    CapabilityReport,
    ClockObservation,
    ConnectionConfig,
    DeviceIdentity,
    DiscoveredDevice,
    EventAuditReport,
    EventRuleStatus,
    MediaChannel,
    MediaResolution,
    Page,
    RecordingQuery,
    RecordingSpan,
)
from .transport import DigestTransport, HttpResponse, Transport

__all__ = [
    "AuthenticationError",
    "CapabilityEvidence",
    "CapabilityReport",
    "ClockObservation",
    "ConnectionConfig",
    "DeviceIdentity",
    "DiscoveredDevice",
    "EventAuditReport",
    "EventRuleStatus",
    "DigestTransport",
    "HikvisionAdapter",
    "discover_devices",
    "parse_discovery_response",
    "HikvisionError",
    "HttpResponse",
    "MediaChannel",
    "MediaResolution",
    "Page",
    "PaginationError",
    "RecordingQuery",
    "RecordingSpan",
    "ResponseLimitError",
    "Transport",
    "UnsafePayloadError",
    "UpstreamError",
]
