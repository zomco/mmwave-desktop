from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tracecue_desktop.errors import MediaError
from tracecue_desktop.media import FFmpegRunner, H264_COMPATIBILITY_ARGS, _with_credentials


def test_credentials_are_percent_encoded_only_at_subprocess_boundary() -> None:
    value = _with_credentials("rtsp://192.0.2.10:554/track", "user@example", "p:a ss")
    expected = "rtsp://" + "user%40example" + ":" + "p%3Aa%20ss" + "@192.0.2.10:554/track"
    assert value == expected


def test_credential_bearing_upstream_locator_is_rejected() -> None:
    unsafe = "rtsp://" + "upstream" + ":" + "secret" + "@192.0.2.10/track"
    with pytest.raises(MediaError) as raised:
        _with_credentials(unsafe, "user", "password")
    assert raised.value.code == "MEDIA_LOCATOR_UNSAFE"


def test_running_subprocess_can_be_cancelled(tmp_path: Path) -> None:
    runner = FFmpegRunner(Path("unused"), Path("unused"), tmp_path)
    checks = 0

    def cancelled() -> bool:
        nonlocal checks
        checks += 1
        return checks >= 2

    with pytest.raises(MediaError) as raised:
        runner._run([sys.executable, "-c", "import time; time.sleep(30)"], cancelled)
    assert raised.value.code == "JOB_CANCELLED"


def test_fallback_uses_packaged_lgpl_h264_encoder(tmp_path: Path) -> None:
    runner = FFmpegRunner(Path("ffmpeg.exe"), Path("ffprobe.exe"), tmp_path)
    commands: list[list[str]] = []

    def run(command: list[str], _cancel_requested=None) -> bool:
        commands.append(command)
        return len(commands) == 2

    runner._run = run  # type: ignore[method-assign]
    runner._render_input(
        "rtsp://192.0.2.10/recording", "operator", "password",
        tmp_path / "clip.mp4.partial", "omit", None,
    )

    assert len(commands) == 2
    assert list(H264_COMPATIBILITY_ARGS) == commands[1][commands[1].index("-c:v"):commands[1].index("-an")]
    assert "libopenh264" in commands[1]
    assert "libx264" not in commands[1]
