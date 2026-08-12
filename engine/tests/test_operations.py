from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from tracecue_engine import (
    Interval,
    Quality,
    calculate_media_window,
    deterministic_interval_id,
    evaluate_quality,
    filter_intervals,
    merge_intervals,
    upsert_by_identity,
    utc_millis,
)


UTC = timezone.utc
START = datetime(2026, 8, 12, 8, 0, tzinfo=UTC)


def interval(identifier: str, start_seconds: int, end_seconds: int, *, gate: str = "pass") -> Interval:
    return Interval(
        id=identifier,
        channel_id="hall",
        event_type="presence.traverse",
        start_at=START + timedelta(seconds=start_seconds),
        end_at=START + timedelta(seconds=end_seconds),
        quality=Quality(gate, 0.9, ("track_continuity",)),
        confidence=0.95,
        tags=("person_related",),
    )


class OperationTests(unittest.TestCase):
    def test_utc_millis_rejects_naive_time(self) -> None:
        with self.assertRaises(ValueError):
            utc_millis(datetime(2026, 1, 1))

    def test_deterministic_id_is_stable(self) -> None:
        first = deterministic_interval_id("source", "hall", "presence.traverse", START, START + timedelta(seconds=1))
        second = deterministic_interval_id("source", "hall", "presence.traverse", START, START + timedelta(seconds=1))
        self.assertEqual(first, second)

    def test_quality_gate_keeps_quality_and_clock_separate(self) -> None:
        result = evaluate_quality(0.95, minimum_score=0.8, clock_healthy=False)
        self.assertEqual("fail", result.gate)
        self.assertIn("clock_unhealthy", result.reasons)

    def test_media_window_applies_rolls(self) -> None:
        item = interval("one", 5, 10)
        window = calculate_media_window(item, pre_roll_ms=5000, post_roll_ms=10000)
        self.assertEqual(START, window.start_at)
        self.assertEqual(START + timedelta(seconds=20), window.end_at)

    def test_upsert_is_idempotent_by_source_and_interval_id(self) -> None:
        item = interval("one", 0, 1)
        state, inserted, updated = upsert_by_identity({}, "source", [item, item])
        self.assertEqual(1, len(state))
        self.assertEqual((1, 0), (inserted, updated))

    def test_filter_defaults_missing_quality_to_unknown(self) -> None:
        unknown = interval("unknown", 0, 1)
        unknown = Interval(
            id=unknown.id,
            channel_id=unknown.channel_id,
            event_type=unknown.event_type,
            start_at=unknown.start_at,
            end_at=unknown.end_at,
        )
        self.assertEqual((unknown,), filter_intervals([unknown], quality_gates={"unknown"}))

    def test_merge_is_deterministic_and_preserves_worst_quality(self) -> None:
        left = interval("left", 0, 3)
        right = interval("right", 4, 8, gate="fail")
        first = merge_intervals([right, left], maximum_gap_ms=1000)
        second = merge_intervals([left, right], maximum_gap_ms=1000)
        self.assertEqual(first, second)
        self.assertEqual(1, len(first))
        self.assertEqual("fail", first[0].quality.gate)
        self.assertEqual(["left", "right"], first[0].attributes["tracecue_engine"]["merged_interval_ids"])


if __name__ == "__main__":
    unittest.main()
