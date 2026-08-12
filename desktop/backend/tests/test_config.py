from pathlib import Path

from tracecue_desktop.config import AppConfig


def test_explicit_media_tool_paths_are_used(monkeypatch, tmp_path: Path) -> None:
    ffmpeg = tmp_path / "custom-ffmpeg"
    ffprobe = tmp_path / "custom-ffprobe"
    monkeypatch.setenv("TRACECUE_FFMPEG_PATH", str(ffmpeg))
    monkeypatch.setenv("TRACECUE_FFPROBE_PATH", str(ffprobe))

    config = AppConfig.default()

    assert config.ffmpeg_path == ffmpeg
    assert config.ffprobe_path == ffprobe
