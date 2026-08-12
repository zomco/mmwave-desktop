"""Rolling source-clock observations and health decisions."""

from __future__ import annotations

import statistics
from collections import deque
from dataclasses import dataclass

from tracecue_engine import utc_millis

from .models import Observation


@dataclass(frozen=True, slots=True)
class ClockPolicy:
    maximum_absolute_skew_ms: int = 30_000
    maximum_jitter_ms: int = 2_000
    minimum_samples: int = 3
    window_samples: int = 30


@dataclass(frozen=True, slots=True)
class ClockSnapshot:
    healthy: bool | None
    estimated_skew_ms: int | None
    jitter_ms: int | None
    sample_count: int
    reason: str


class ClockHealth:
    def __init__(self, policy: ClockPolicy | None = None):
        self.policy = policy or ClockPolicy()
        self._skews: deque[int] = deque(maxlen=self.policy.window_samples)

    def observe(self, observation: Observation) -> ClockSnapshot:
        skew = utc_millis(observation.source_at) - utc_millis(observation.received_at)
        self._skews.append(skew)
        return self.snapshot()

    def snapshot(self) -> ClockSnapshot:
        count = len(self._skews)
        if not count:
            return ClockSnapshot(None, None, None, 0, "no_clock_observations")
        estimated = int(statistics.median(self._skews))
        jitter = int(max(self._skews) - min(self._skews))
        if count < self.policy.minimum_samples:
            return ClockSnapshot(None, estimated, jitter, count, "insufficient_clock_observations")
        if abs(estimated) > self.policy.maximum_absolute_skew_ms:
            return ClockSnapshot(False, estimated, jitter, count, "clock_skew_exceeds_policy")
        if jitter > self.policy.maximum_jitter_ms:
            return ClockSnapshot(False, estimated, jitter, count, "clock_jitter_exceeds_policy")
        return ClockSnapshot(True, estimated, jitter, count, "clock_healthy")

