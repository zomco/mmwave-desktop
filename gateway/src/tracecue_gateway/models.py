"""Gateway observation values isolated from product interval models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Observation:
    source_id: str
    channel_id: str
    track_id: str
    source_at: datetime
    received_at: datetime
    x: float
    y: float

