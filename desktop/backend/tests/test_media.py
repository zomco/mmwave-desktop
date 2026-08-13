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
        return True

    runner._run = run  # type: ignore[method-assign]
    runner._render_input(
        "rtsp://192.0.2.10/recording", "operator", "password",
        tmp_path / "clip.mp4.partial", "omit", None, force_h264=True,
    )

    assert len(commands) == 1
    assert list(H264_COMPATIBILITY_ARGS) == commands[0][commands[0].index("-c:v"):commands[0].index("-an")]
    assert "libopenh264" in commands[0]
    assert "libx264" not in commands[0]


def test_preferred_audio_falls_back_to_video_only(tmp_path: Path) -> None:
    runner = FFmpegRunner(Path("ffmpeg.exe"), Path("ffprobe.exe"), tmp_path)
    commands: list[list[str]] = []

    def run(command: list[str], _cancel_requested=None) -> bool:
        commands.append(command)
        return "-an" in command

    runner._run = run  # type: ignore[method-assign]
    runner._render_input(
        "rtsp://192.0.2.10/recording", "operator", "password",
        tmp_path / "clip.mp4.partial", "prefer", None,
    )

    assert len(commands) == 2
    assert "-c:a" in commands[0]
    assert "-an" in commands[1]


def test_non_h264_input_is_transcoded_without_a_full_copy_pass(tmp_path: Path) -> None:
    runner = FFmpegRunner(Path("ffmpeg.exe"), Path("ffprobe.exe"), tmp_path)
    commands: list[list[str]] = []
    runner._probe_video_codec = lambda *_args: "hevc"  # type: ignore[method-assign]
    runner._verify = lambda _path: {  # type: ignore[method-assign]
        "video_codec": "h264", "audio_codec": None, "duration_seconds": 10.0,
    }
    runner._run = lambda command, _cancel_requested=None: commands.append(command) or True  # type: ignore[method-assign]

    runner._render_compatible_input(
        "rtsp://192.0.2.10/recording", "operator", "password",
        tmp_path / "clip.mp4.partial", "omit", None,
    )

    assert len(commands) == 1
    assert "libopenh264" in commands[0]
    assert "copy" not in commands[0]


def test_preview_uses_video_only_single_frame_command(tmp_path: Path) -> None:
    runner = FFmpegRunner(Path("ffmpeg.exe"), Path("ffprobe.exe"), tmp_path)
    commands: list[list[str]] = []

    def run(command: list[str], _cancel_requested=None) -> bool:
        commands.append(command)
        output = Path(command[-1])
        output.write_bytes(b"\xff\xd8\xffpreview")
        return True

    runner._run = run  # type: ignore[method-assign]
    output = runner.generate_preview(
        preview_id="preview_abc123",
        playback_locator="rtsp://192.0.2.10/recording",
        username="operator",
        password="password",
    )

    assert output.name == "preview_abc123.jpg"
    assert "-frames:v" in commands[0]
    assert commands[0][commands[0].index("-frames:v") + 1] == "1"
    assert "-an" not in commands[0]


def test_render_applies_requested_output_duration(tmp_path: Path) -> None:
    runner = FFmpegRunner(Path("ffmpeg.exe"), Path("ffprobe.exe"), tmp_path)
    commands: list[list[str]] = []
    runner._run = lambda command, _cancel_requested=None: commands.append(command) or True  # type: ignore[method-assign]

    runner._render_input(
        "rtsp://192.0.2.10/recording", "operator", "password",
        tmp_path / "clip.mp4.partial", "omit", None, max_duration_seconds=30,
    )

    assert commands[0][commands[0].index("-t") + 1] == "30"


def test_animation_is_bounded_webp_and_atomic(tmp_path: Path) -> None:
    runner = FFmpegRunner(Path("ffmpeg.exe"), Path("ffprobe.exe"), tmp_path)
    commands: list[list[str]] = []

    def run(command: list[str], _cancel_requested=None) -> bool:
        commands.append(command)
        Path(command[-1]).write_bytes(b"RIFF0000WEBPfixture")
        return True

    runner._run = run  # type: ignore[method-assign]
    output = runner.generate_animation(
        animation_id="animation_abc123",
        playback_locator="rtsp://192.0.2.10/recording",
        username="operator",
        password="password",
        duration_seconds=3,
    )

    assert output.name == "animation_abc123.webp"
    assert commands[0][commands[0].index("-t") + 1] == "3"
    assert "libwebp_anim" in commands[0]
