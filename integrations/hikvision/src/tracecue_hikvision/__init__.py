"""Public Hikvision adapter API."""

from .adapter import HikvisionAdapter
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
    "DigestTransport",
    "HikvisionAdapter",
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

