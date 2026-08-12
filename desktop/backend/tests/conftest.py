from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from tracecue_desktop.config import AppConfig
from tracecue_desktop.media import MediaResult
from tracecue_desktop.secrets import InMemorySecretStore
from tracecue_desktop.services import DesktopServices
from tracecue_hikvision import (
    CapabilityEvidence,
    CapabilityReport,
    ClockObservation,
    DeviceIdentity,
    HikvisionAdapter,
    MediaChannel,
    Page,
    RecordingSpan,
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

    def search_all_recordings(self, query):
        return self.spans

    def search_recordings(self, query):
        return Page(self.spans, None, True)

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
        self, *, clip_id, playback_locators, username, password, audio_policy, cancel_requested
    ):
        assert password == "secret-password"
        assert playback_locators == ("rtsp://192.0.2.10/fixture",)
        assert not cancel_requested()
        output = self.clip_root / f"{clip_id}.mp4"
        output.write_bytes(b"0123456789" * 100)
        return MediaResult(output, output.stat().st_size, "h264", "aac", 60.0)


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
