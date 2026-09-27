"""Always-on fusion review loop. No Home Assistant.

Tracking comes from the mmwave-engine package. Stills and short clips are cut
from a live stream, not from an NVR timeline.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from mmwave_engine.frames import parse_target_frame
from mmwave_engine.fusion import FusionEngine, observations_inside
from mmwave_engine.events import ZoneEventEngine
from mmwave_engine.quality import TrajectoryQualityEngine
from mmwave_engine.radar import observations_from_frame
from mmwave_engine.recording import plan_recordings

from .fusion_store import FusionEventStore

LOOSE_QUALITY = {
    "history_s": 60.0,
    "smoothing_s": 0.5,
    "min_duration_s": 0.0,
    "min_observed_points": 1,
    "min_displacement_cm": 0.0,
    "min_observed_ratio": 0.0,
    "min_inside_ratio": 0.0,
    "max_gap_s": 30.0,
    "max_jump_cm": 1000.0,
    "require_enter_exit": False,
    "min_score": 0,
    "boundary_margin_cm": 60.0,
    "persist_interval_s": 0.5,
}


class ClipSink(Protocol):
    def snapshot(self, entity_id: str, filename: str) -> None: ...

    def record(self, entity_id: str, filename: str, lookback: int, duration: int) -> None: ...


def ffmpeg_snapshot_argv(rtsp_url: str, filename: str) -> list[str]:
    return ["ffmpeg", "-y", "-i", rtsp_url, "-frames:v", "1", filename]


def ffmpeg_record_argv(rtsp_url: str, filename: str, duration: int) -> list[str]:
    return ["ffmpeg", "-y", "-i", rtsp_url, "-t", str(duration), "-c", "copy", filename]


class FfmpegClipSink:
    """Cut a still, then a short clip, from a live RTSP URL. No NVR seek.

    ``lookback`` is ignored: a live URL has no timeline to rewind.
    """

    def __init__(self, streams: dict[str, str]) -> None:
        self.streams = streams

    def snapshot(self, entity_id: str, filename: str) -> None:
        url = self.streams.get(entity_id)
        if not url:
            return
        _run(ffmpeg_snapshot_argv(url, filename))

    def record(self, entity_id: str, filename: str, lookback: int, duration: int) -> None:
        url = self.streams.get(entity_id)
        if not url:
            return
        _run(ffmpeg_record_argv(url, filename, duration))


def _run(argv: list[str]) -> None:
    import subprocess

    subprocess.run(argv, check=False, capture_output=True)


class FileClipSink:
    """Test and offline sink. Writes placeholder files; does not spawn FFmpeg."""

    def snapshot(self, entity_id: str, filename: str) -> None:
        path = Path(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\xff\xd8\xff\xd9")

    def record(self, entity_id: str, filename: str, lookback: int, duration: int) -> None:
        path = Path(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"ftyp")


class FusionReviewLoop:
    """Ingest v1 frames and keep events even if the review UI is closed."""

    def __init__(
        self,
        store: FusionEventStore,
        *,
        zones: list[dict[str, object]],
        room_w: float = 800.0,
        room_d: float = 600.0,
        calibration: dict[str, object] | None = None,
        cameras: list[dict[str, object]] | None = None,
        sink: ClipSink | None = None,
        media_root: str = "media",
    ) -> None:
        self.store = store
        self.room_w = room_w
        self.room_d = room_d
        self.calibration = calibration or {"radar_x": 0, "radar_y": 0, "radar_z": 220, "yaw": 0, "pitch": 0, "roll": 0}
        self.cameras = cameras or []
        self.sink = sink or FileClipSink()
        self.media_root = media_root
        self.engine = FusionEngine(confirm_hits=1, track_ttl_s=1.0, min_confirm_sources=1)
        self.zones = ZoneEventEngine("desktop", zones)
        self.quality = TrajectoryQualityEngine("desktop", room_w, room_d, LOOSE_QUALITY)
        self._last_recordings: dict[tuple[str, str, str], float] = {}

    def ingest_frame(self, payload: str, now: float, radar_id: str = "radar") -> list[dict[str, object]]:
        frame = parse_target_frame(payload)
        if frame is None:
            raise ValueError("payload is not a v1 target frame")
        observations = observations_from_frame(
            radar_id,
            frame,
            self.calibration,
            scale=1.0,
            timestamp=now,
            weight=1.0,
        )
        result = self.engine.step(
            observations_inside(observations, self.room_w, self.room_d, None),
            now,
        )
        self.quality.observe(result.tracks, now)
        events = self.zones.evaluate(result.tracks, now)
        self.quality.add_zone_events(events)
        for track_id in result.merged_track_ids:
            self.quality.discard(track_id)
        for track_id in result.ended_track_ids:
            finished = self.quality.finish(track_id, now)
            if finished is not None:
                events.append(finished[0])
        saved: list[dict[str, object]] = []
        for event in events:
            self._attach_media(event, now)
            self.store.save(event)
            saved.append(event)
        return saved

    def _attach_media(self, event: dict[str, object], now: float) -> None:
        plans = plan_recordings(event, self.cameras, self._last_recordings, now, "desktop", self.media_root)
        event["recording_decisions"] = [
            {"camera_entity_id": plan.camera_entity_id, "status": plan.status} for plan in plans
        ]
        for plan in plans:
            if plan.status != "scheduled" or plan.clip is None or plan.recording_key is None:
                continue
            self.sink.snapshot(plan.camera_entity_id, str(Path(plan.absolute_path).with_suffix(".jpg")))
            self.sink.record(plan.camera_entity_id, plan.absolute_path, plan.lookback, plan.duration)
            self._last_recordings[plan.recording_key] = float(event["timestamp"])
            event["snapshot_path"] = str(Path(plan.clip["path"]).with_suffix(".jpg"))
            event["clip_path"] = plan.clip["path"]
