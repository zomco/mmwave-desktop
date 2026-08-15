from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from tracecue_desktop.config import AppConfig
from tracecue_desktop.media import MediaResult, SampledFrames
from tracecue_desktop.secrets import InMemorySecretStore
from tracecue_desktop.services import DesktopServices
from tracecue_desktop.vision import VisualAnalysisResult
from tracecue_hikvision import (
    CapabilityEvidence,
    CapabilityReport,
    CameraDeviceDetails,
    ClockObservation,
    DeviceDetailsReport,
    DeviceIdentity,
    DiscoveredDevice,
    EventAuditReport,
    EventRuleStatus,
    HistoricalEvent,
    HistoricalEventResult,
    HikvisionAdapter,
    MediaChannel,
    NvrDeviceDetails,
    Page,
    RecordingSpan,
    RuleOverlay,
)


NOW = datetime(2026, 8, 12, 8, 0, tzinfo=timezone.utc)


class FakeAdapter:
    def __init__(self) -> None:
        self.spans = (
            RecordingSpan(
                NOW,
                NOW.replace(minute=1),
                "motion",
                "rtsp://192.0.2.10/fixture",
                "fixture-recording-1",
            ),
        )

    def probe(self) -> CapabilityReport:
        evidence = (
            CapabilityEvidence("device_info", "supported", "/device", 200, "abc", NOW),
            CapabilityEvidence("channel_discovery", "supported", "/channels", 200, "def", NOW),
            CapabilityEvidence("record_search", "supported", "/search", 200, "ghi", NOW),
        )
        return CapabilityReport(
            True,
            True,
            DeviceIdentity("fixture-nvr", "fixture-firmware", "must-not-leak"),
            ClockObservation(NOW, NOW, NOW, 0, "+00:00"),
            evidence,
            (),
        )

    def list_channels(self):
        return (MediaChannel("1", "Front door", True, 1, ("101",)),)

    def inspect_device_details(self):
        return DeviceDetailsReport(
            NOW,
            NvrDeviceDetails(
                "Fixture NVR", "NVR", "fixture-nvr", "fixture-firmware",
                "must-not-leak", "00:00:00:00:00:00", "255", "20260812",
                "fixture-encoder", "20260811",
            ),
            (
                CameraDeviceDetails(
                    "1", "Front door", True, "fixture-camera", "camera-firmware",
                    "camera-serial", "camera-device", "HIKVISION", "192.0.2.41", 8000, 1, "main",
                ),
            ),
        )

    def search_all_recordings(self, query):
        return self.spans

    def search_recordings(self, query):
        return Page(self.spans, None, True)

    def search_historical_events(self, query):
        items = ()
        if query.start_at <= NOW < query.end_at and (not query.event_types or "motion" in query.event_types):
            items = (
                HistoricalEvent(
                    "1",
                    "motion",
                    NOW,
                    "log.hikvision.com/Alarm/motionStart/1",
                    "fixture-event-1",
                    NOW.replace(second=9),
                ),
            )
        elif query.start_at <= NOW < query.end_at and "line_crossing" in query.event_types:
            items = (
                HistoricalEvent(
                    "1", "line_crossing", NOW,
                    "log.hikvision.com/Alarm/lineDetection/1", "fixture-line-event-1",
                    NOW.replace(second=9),
                ),
            )
        return HistoricalEventResult(items)

    def inspect_event_settings(self, channels):
        return EventAuditReport(
            NOW,
            (
                EventRuleStatus(
                    "1", "101", "motion", "supported", True, True,
                    60, 1, 1, "/motionDetection",
                ),
                EventRuleStatus(
                    "1", "101", "line_crossing", "supported", True, True,
                    60, 1, 1, "/lineDetection", overlays=(
                        RuleOverlay("line", 1000, 1000, ((500, 0), (500, 1000))),
                    ),
                ),
            ),
        )

    resolve_media = staticmethod(HikvisionAdapter.resolve_media)


class FakeMediaRunner:
    def __init__(self, clip_root: Path):
        self.clip_root = clip_root

    def availability(self):
        return {
            "ffmpeg": {"available": True, "version": "fixture"},
            "ffprobe": {"available": True, "version": "fixture"},
        }

    def generate(
        self, *, clip_id, playback_locators, username, password, audio_policy,
        max_duration_seconds, cancel_requested
    ):
        assert password == "secret-password"
        assert len(playback_locators) == 1
        assert playback_locators[0].startswith("rtsp://192.0.2.10/fixture?")
        assert "starttime=" in playback_locators[0] and "endtime=" in playback_locators[0]
        assert max_duration_seconds > 0
        assert not cancel_requested()
        output = self.clip_root / f"{clip_id}.mp4"
        output.write_bytes(b"0123456789" * 100)
        return MediaResult(output, output.stat().st_size, "h264", "aac", 60.0)

    def generate_preview(
        self, *, preview_id, playback_locator, username, password, cancel_requested
    ):
        assert password == "secret-password"
        assert playback_locator.startswith("rtsp://192.0.2.10/fixture?")
        output = self.clip_root / "previews" / f"{preview_id}.jpg"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"\xff\xd8\xfffixture-preview")
        return output

    def generate_snapshot(
        self, *, snapshot_id, live_locator, username, password, cancel_requested
    ):
        assert live_locator == "rtsp://192.0.2.10:554/Streaming/Channels/101"
        assert password == "secret-password"
        output = self.clip_root / "snapshots" / f"{snapshot_id}.jpg"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"\xff\xd8\xfffixture-snapshot")
        return output

    def generate_animation(
        self, *, animation_id, playback_locator, username, password,
        duration_seconds, cancel_requested
    ):
        assert playback_locator.startswith("rtsp://192.0.2.10/fixture?")
        assert 1 <= duration_seconds <= 5
        output = self.clip_root / "animations" / f"{animation_id}.webp"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"RIFFfixtureWEBP")
        return output

    def sample_bgr_frames(
        self, *, playback_locator, username, password, duration_seconds,
        width, height, fps, cancel_requested
    ):
        assert playback_locator.startswith("rtsp://192.0.2.10/fixture?")
        assert password == "secret-password"
        assert 1 <= duration_seconds <= 30
        assert not cancel_requested()
        return SampledFrames(width, height, fps, (bytes(width * height * 3),) * 3)


class FakeVisualAnalyzer:
    def availability(self):
        return {
            "available": True,
            "code": None,
            "message": "fixture visual analyzer",
            "model_id": "fixture-model:abc",
            "supported_event_types": ["line_crossing", "region_intrusion"],
            "target_classes": ["person"],
        }

    def analyze(self, *, frames, width, height, fps, event_type, overlays):
        assert len(frames) == 3
        assert (width, height, fps) == (416, 416, 5)
        assert event_type in {"line_crossing", "region_intrusion"}
        return VisualAnalysisResult(
            "confirmed_trigger", "trajectory_matches_rule", 0.91, 2_000,
            ("person",), 1, 3, 3, "fixture-model:abc",
        )


class FakeShareServer:
    def __init__(self) -> None:
        self.stopped = False

    def create_share(self, *, clip_id, path, title, route_target):
        assert path.is_file()
        assert title == "Front door"
        assert route_target == "192.0.2.10"
        return {
            "clip_id": clip_id,
            "url": "http://192.0.2.55:54321/s/fixture-token",
            "expires_at_ms": 1_786_528_900_000,
        }

    def stop(self) -> None:
        self.stopped = True


@pytest.fixture
def services(tmp_path: Path) -> DesktopServices:
    config = AppConfig(
        data_dir=tmp_path / "data",
        clip_dir=tmp_path / "clips",
        ffmpeg_path=Path("missing-ffmpeg"),
        ffprobe_path=Path("missing-ffprobe"),
    )
    adapter = FakeAdapter()
    return DesktopServices(
        config,
        secret_store=InMemorySecretStore(),
        adapter_factory=lambda _: adapter,
        media_runner=FakeMediaRunner(config.clip_dir),
        share_server=FakeShareServer(),
        device_discoverer=lambda _timeout: (
            DiscoveredDevice(
                "192.0.2.20", 80, False, "Discovered recorder", "fixture-discovery", ("NetworkVideoTransmitter",)
            ),
        ),
        visual_analyzer=FakeVisualAnalyzer(),
    )


@pytest.fixture
def nvr(services: DesktopServices):
    return services.create_nvr(
        {
            "name": "Fixture NVR",
            "host": "192.0.2.10",
            "username": "fixture-user",
            "password": "secret-password",
            "http_port": 80,
            "use_https": False,
            "verify_tls": True,
        }
    )
