"""Bounded short-track detector producing deterministic traverse intervals."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import timedelta

from tracecue_engine import (
    Interval,
    MediaWindow,
    Quality,
    SourceRef,
    deterministic_interval_id,
    evaluate_quality,
    utc_millis,
)

from .clock import ClockSnapshot
from .models import Observation


@dataclass(frozen=True, slots=True)
class TraversePolicy:
    left_boundary_x: float = -1.0
    right_boundary_x: float = 1.0
    minimum_points: int = 4
    minimum_duration_ms: int = 200
    maximum_duration_ms: int = 60_000
    maximum_gap_ms: int = 1_000
    maximum_tracks: int = 128
    pre_roll_ms: int = 5_000
    post_roll_ms: int = 10_000
    minimum_quality_score: float = 0.75


class TraverseDetector:
    def __init__(self, source_id: str, channel_id: str, policy: TraversePolicy | None = None):
        self.source_id = source_id
        self.channel_id = channel_id
        self.policy = policy or TraversePolicy()
        self._tracks: dict[str, deque[Observation]] = defaultdict(lambda: deque(maxlen=256))
        self._completed: set[str] = set()

    def ingest(self, observation: Observation, clock: ClockSnapshot) -> Interval | None:
        if observation.source_id != self.source_id or observation.channel_id != self.channel_id:
            raise ValueError("observation source/channel does not match the detector")
        if observation.track_id in self._completed:
            return None
        self._expire(observation)
        track = self._tracks[observation.track_id]
        if track and observation.source_at <= track[-1].source_at:
            return None
        track.append(observation)
        if len(track) < self.policy.minimum_points:
            return None
        first, last = track[0], track[-1]
        direction = None
        if first.x <= self.policy.left_boundary_x and last.x >= self.policy.right_boundary_x:
            direction = "left_to_right"
        elif first.x >= self.policy.right_boundary_x and last.x <= self.policy.left_boundary_x:
            direction = "right_to_left"
        if direction is None:
            return None
        duration = utc_millis(last.source_at) - utc_millis(first.source_at)
        gaps = [
            utc_millis(right.source_at) - utc_millis(left.source_at)
            for left, right in zip(track, list(track)[1:])
        ]
        continuous = max(gaps, default=0) <= self.policy.maximum_gap_ms
        duration_valid = self.policy.minimum_duration_ms <= duration <= self.policy.maximum_duration_ms
        displacement = abs(last.x - first.x)
        points_score = min(1.0, len(track) / max(self.policy.minimum_points * 2, 1))
        continuity_score = 1.0 if continuous else 0.0
        crossing_score = min(1.0, displacement / max(self.policy.right_boundary_x - self.policy.left_boundary_x, 0.001))
        score = round(points_score * 0.25 + continuity_score * 0.4 + crossing_score * 0.35, 4)
        quality = evaluate_quality(
            score,
            minimum_score=self.policy.minimum_quality_score,
            required_observations_present=duration_valid and len(track) >= self.policy.minimum_points,
            clock_healthy=clock.healthy is True,
            reasons=("valid_zone_crossing",) if direction else (),
        )
        self._completed.add(observation.track_id)
        interval_id = deterministic_interval_id(
            self.source_id,
            self.channel_id,
            "presence.traverse",
            first.source_at,
            last.source_at,
            source_identity=observation.track_id,
        )
        return Interval(
            id=interval_id,
            channel_id=self.channel_id,
            event_type="presence.traverse",
            start_at=first.source_at,
            end_at=last.source_at,
            quality=Quality(quality.gate, quality.score, quality.reasons),
            confidence=score,
            media_window=MediaWindow(
                first.source_at - timedelta(milliseconds=self.policy.pre_roll_ms),
                last.source_at + timedelta(milliseconds=self.policy.post_roll_ms),
            ),
            tags=("person_related",),
            source_ref=SourceRef(track_id=observation.track_id),
            attributes={
                "tracecue_gateway": {
                    "direction": direction,
                    "point_count": len(track),
                    "clock_skew_ms": clock.estimated_skew_ms,
                }
            },
        )

    def _expire(self, observation: Observation) -> None:
        cutoff = utc_millis(observation.source_at) - self.policy.maximum_duration_ms
        for track_id in list(self._tracks):
            track = self._tracks[track_id]
            while track and utc_millis(track[0].source_at) < cutoff:
                track.popleft()
            if not track:
                del self._tracks[track_id]
        if len(self._tracks) >= self.policy.maximum_tracks and observation.track_id not in self._tracks:
            oldest = min(self._tracks, key=lambda key: self._tracks[key][-1].source_at)
            del self._tracks[oldest]

