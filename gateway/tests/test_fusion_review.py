"""Fusion review survives without Home Assistant and without the review UI."""

from __future__ import annotations

import json
from threading import Thread
from urllib.request import urlopen

import pytest

pytest.importorskip("mmwave_engine")

from tracecue_gateway.fusion_review import (  # noqa: E402
    FusionReviewLoop,
    ffmpeg_record_argv,
    ffmpeg_snapshot_argv,
)
from tracecue_gateway.fusion_store import FusionEventStore  # noqa: E402
from tracecue_gateway.resident import bind_events  # noqa: E402

ZONE = [{"id": "hall", "dwell_s": 0, "polygon": [{"x": 0, "y": 0}, {"x": 90, "y": 0}, {"x": 90, "y": 200}, {"x": 0, "y": 200}]}]
CAMERA = [{
    "entity_id": "camera.hall",
    "zones": ["hall"],
    "event_types": ["enter", "dwell", "traverse"],
    "lookback": 1,
    "duration": 2,
    "cooldown_s": 60,
    "buffer_seconds": 5,
}]


def frame(index: int, x: float, y: float) -> str:
    return '{"v":1,"f":%d,"ts":%d,"t":[[%s,%s,0]]}' % (index, index * 100, x, y)


def test_enter_is_kept_after_the_review_ui_is_gone(tmp_path) -> None:
    store = FusionEventStore(tmp_path / "events.sqlite")
    loop = FusionReviewLoop(store, zones=ZONE, cameras=CAMERA, media_root=str(tmp_path / "media"))
    saved = loop.ingest_frame(frame(1, 80, 80), now=1_000.0)
    assert [item["event_type"] for item in saved] == ["enter"]
    reopened = FusionEventStore(tmp_path / "events.sqlite")
    assert reopened.list_events()[0]["zone_id"] == "hall"
    assert reopened.list_events()[0]["snapshot_path"].endswith(".jpg")


def test_exit_does_not_schedule_a_clip(tmp_path) -> None:
    store = FusionEventStore(tmp_path / "events.sqlite")
    loop = FusionReviewLoop(store, zones=ZONE, cameras=CAMERA, media_root=str(tmp_path / "media"))
    loop.ingest_frame(frame(1, 80, 80), now=1_000.0)
    left = loop.ingest_frame(frame(2, 160, 80), now=1_000.4)
    exits = [item for item in left if item["event_type"] == "exit"]
    assert exits
    assert exits[0]["recording_decisions"][0]["status"] == "event_type_filtered"


def test_ffmpeg_argv_is_a_list_without_a_shell() -> None:
    snapshot = ffmpeg_snapshot_argv("rtsp://camera/live", "still.jpg")
    record = ffmpeg_record_argv("rtsp://camera/live", "clip.mp4", 8)
    assert snapshot[0] == "ffmpeg"
    assert record[0] == "ffmpeg"
    assert all(" " not in arg or arg.startswith("rtsp://") for arg in snapshot + record)


def test_resident_lists_events_without_an_nvr(tmp_path) -> None:
    store = FusionEventStore(tmp_path / "events.sqlite")
    store.save({"event_id": "e1", "event_type": "enter", "zone_id": "hall", "timestamp": 1.0})
    server = bind_events(store, "127.0.0.1", 0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        with urlopen(f"http://127.0.0.1:{port}/events", timeout=2) as response:
            payload = json.loads(response.read())
        assert payload[0]["event_id"] == "e1"
    finally:
        server.shutdown()
