"""Public API for the TraceCue interval engine."""

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
from .operations import (
    QualityGateResult,
    calculate_media_window,
    deterministic_interval_id,
    evaluate_quality,
    filter_intervals,
    from_utc_millis,
    merge_intervals,
    upsert_by_identity,
    utc_millis,
)
from .timeline import (
    MAX_TIMELINE_BYTES,
    TimelineInspection,
    dump_timeline,
    inspect_timeline,
    load_timeline,
    parse_rfc3339,
)

__all__ = [
    "Coverage",
    "ExternalRef",
    "Interval",
    "MAX_TIMELINE_BYTES",
    "MediaWindow",
    "Producer",
    "Quality",
    "QualityGateResult",
    "SourceChannel",
    "SourceRef",
    "TimelineDocument",
    "TimelineInspection",
    "TimelineValidationError",
    "ValidationIssue",
    "calculate_media_window",
    "deterministic_interval_id",
    "dump_timeline",
    "evaluate_quality",
    "filter_intervals",
    "from_utc_millis",
    "inspect_timeline",
    "load_timeline",
    "merge_intervals",
    "parse_rfc3339",
    "upsert_by_identity",
    "utc_millis",
]

