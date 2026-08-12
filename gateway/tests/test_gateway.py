from __future__ import annotations

from datetime import datetime, timedelta, timezone

from tracecue_engine import SourceChannel, dump_timeline, inspect_timeline
from tracecue_gateway import (
    ClockHealth,
    ClockPolicy,
    GatewayService,
    GatewayStore,
    Observation,
    ReplayAdapter,
    TraverseDetector,
    TraversePolicy,
)


START = datetime(2026, 8, 12, 8, 0, tzinfo=timezone.utc)


def observations(skew_ms: int = 0):
    values = [-1.2, -0.4, 0.4, 1.2]
    return [
        Observation(
            "gateway-fixture",
            "hall-radar",
            "track-1",
            START + timedelta(milliseconds=index * 300),
            START + timedelta(milliseconds=index * 300 - skew_ms),
            x,
            0.0,
        )
        for index, x in enumerate(values)
    ]


def test_clock_health_requires_samples_and_rejects_skew() -> None:
    healthy = ClockHealth(ClockPolicy(minimum_samples=3))
    snapshots = [healthy.observe(item) for item in observations()]
    assert snapshots[0].healthy is None
    assert snapshots[-1].healthy is True
    unhealthy = ClockHealth(ClockPolicy(minimum_samples=3, maximum_absolute_skew_ms=1000))
    assert [unhealthy.observe(item) for item in observations(5_000)][-1].healthy is False


def test_gateway_persists_deterministic_interval_while_desktop_is_offline(tmp_path) -> None:
    store = GatewayStore(tmp_path / "gateway.sqlite", diagnostic_limit=3)
    replay = ReplayAdapter(observations())
    service = GatewayService(
        replay,
        TraverseDetector(
            "gateway-fixture",
            "hall-radar",
            TraversePolicy(minimum_points=4, minimum_quality_score=0.7),
        ),
        ClockHealth(ClockPolicy(minimum_samples=3)),
        store,
    )
    outcomes = [service.process_once() for _ in range(4)]
    assert outcomes == [False, False, False, True]
    assert store.interval_count() == 1

    document = store.export(
        source_id="gateway-fixture",
        channel=SourceChannel("hall-radar", "Hall radar", "mmwave"),
        start_at=START - timedelta(seconds=1),
        end_at=START + timedelta(seconds=2),
        complete=True,
    )
    reparsed = inspect_timeline(dump_timeline(document)).document
    assert len(reparsed.intervals) == 1
    assert reparsed.intervals[0].event_type == "presence.traverse"
    assert reparsed.intervals[0].quality.gate == "pass"


def test_unhealthy_clock_retains_interval_but_fails_quality_gate(tmp_path) -> None:
    store = GatewayStore(tmp_path / "unhealthy.sqlite")
    service = GatewayService(
        ReplayAdapter(observations(60_000)),
        TraverseDetector("gateway-fixture", "hall-radar", TraversePolicy(minimum_quality_score=0.7)),
        ClockHealth(ClockPolicy(minimum_samples=2)),
        store,
    )
    for _ in range(4):
        service.process_once()
    exported = store.export(
        source_id="gateway-fixture",
        channel=SourceChannel("hall-radar", "Hall radar", "mmwave"),
        start_at=START - timedelta(seconds=1),
        end_at=START + timedelta(seconds=2),
        complete=False,
    )
    assert exported.intervals[0].quality.gate == "fail"
    assert "clock_unhealthy" in exported.intervals[0].quality.reasons
