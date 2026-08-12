"""FFmpeg clip generation using argument arrays and atomic completion."""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import quote, urlsplit, urlunsplit

from .errors import MediaError


H264_COMPATIBILITY_ARGS = (
    "-c:v", "libopenh264",
    "-b:v", "4M",
    "-maxrate", "6M",
    "-bufsize", "8M",
    "-pix_fmt", "yuv420p",
)


@dataclass(frozen=True, slots=True)
class MediaResult:
    path: Path
    size_bytes: int
    video_codec: str
    audio_codec: str | None
    duration_seconds: float


class FFmpegRunner:
    def __init__(
        self,
        ffmpeg_path: Path,
        ffprobe_path: Path,
        clip_root: Path,
        *,
        connection_timeout_seconds: int = 10,
        total_timeout_seconds: int = 300,
    ):
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path
        self.clip_root = clip_root.resolve()
        self.connection_timeout_seconds = connection_timeout_seconds
        self.total_timeout_seconds = total_timeout_seconds

    def availability(self) -> dict[str, object]:
        return {
            "ffmpeg": self._version(self.ffmpeg_path),
            "ffprobe": self._version(self.ffprobe_path),
        }

    def generate(
        self,
        *,
        clip_id: str,
        playback_locators: tuple[str, ...],
        username: str,
        password: str,
        audio_policy: str = "prefer",
        cancel_requested: Callable[[], bool] | None = None,
    ) -> MediaResult:
        if not playback_locators:
            raise MediaError("RECORDING_NOT_FOUND", "No playable NVR recording covers the request.", 409)
        if audio_policy not in {"prefer", "preserve", "omit"}:
            raise MediaError("MEDIA_POLICY_INVALID", "Unsupported audio policy.", 400)
        self.clip_root.mkdir(parents=True, exist_ok=True)
        output = self._safe_output(clip_id)
        partial = output.with_suffix(output.suffix + ".partial")
        segment_paths: list[Path] = []
        try:
            if len(playback_locators) == 1:
                self._render_input(
                    playback_locators[0], username, password, partial, audio_policy, cancel_requested
                )
            else:
                for index, locator in enumerate(playback_locators):
                    segment = self.clip_root / f".{clip_id}.segment-{index}.mp4"
                    segment_partial = segment.with_suffix(segment.suffix + ".partial")
                    self._render_input(
                        locator, username, password, segment_partial, audio_policy, cancel_requested
                    )
                    segment_partial.replace(segment)
                    segment_paths.append(segment)
                self._concat_segments(segment_paths, partial, cancel_requested)
            metadata = self._verify(partial)
            partial.replace(output)
            return MediaResult(
                output,
                output.stat().st_size,
                metadata["video_codec"],
                metadata["audio_codec"],
                metadata["duration_seconds"],
            )
        except MediaError:
            raise
        except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError) as exc:
            raise MediaError("MEDIA_GENERATION_FAILED", "FFmpeg could not create a playable clip.", 500) from exc
        finally:
            partial.unlink(missing_ok=True)
            for segment in segment_paths:
                segment.unlink(missing_ok=True)

    def _render_input(
        self,
        locator: str,
        username: str,
        password: str,
        output: Path,
        audio_policy: str,
        cancel_requested: Callable[[], bool] | None,
    ) -> None:
        authenticated = _with_credentials(locator, username, password)
        audio_args = {
            "prefer": ["-c:a", "aac", "-b:a", "128k"],
            "preserve": ["-c:a", "copy"],
            "omit": ["-an"],
        }[audio_policy]
        common = [
            str(self.ffmpeg_path), "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
            "-rtsp_transport", "tcp", "-timeout", str(self.connection_timeout_seconds * 1_000_000),
            "-i", authenticated,
        ]
        copy_command = common + ["-map", "0:v:0", "-map", "0:a?", "-c:v", "copy"] + audio_args + [
            "-movflags", "+faststart", "-f", "mp4", str(output)
        ]
        if self._run(copy_command, cancel_requested):
            return
        transcode_command = common + [
            "-map", "0:v:0", "-map", "0:a?", *H264_COMPATIBILITY_ARGS,
        ] + audio_args + ["-movflags", "+faststart", "-f", "mp4", str(output)]
        if not self._run(transcode_command, cancel_requested):
            raise MediaError("MEDIA_CODEC_UNSUPPORTED", "The recording could not be remuxed or transcoded.", 422)

    def _concat_segments(
        self,
        segments: list[Path],
        output: Path,
        cancel_requested: Callable[[], bool] | None,
    ) -> None:
        concat_file = self.clip_root / f".{output.stem}.concat.txt"
        try:
            lines = ["file '" + str(path).replace("'", "'\\''") + "'" for path in segments]
            concat_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
            command = [
                str(self.ffmpeg_path), "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy",
                "-movflags", "+faststart", "-f", "mp4", str(output),
            ]
            if not self._run(command, cancel_requested):
                raise MediaError("MEDIA_CONCAT_FAILED", "Recording segments could not be joined.", 422)
        finally:
            concat_file.unlink(missing_ok=True)

    def _verify(self, path: Path) -> dict[str, object]:
        command = [
            str(self.ffprobe_path), "-v", "error", "-show_streams", "-show_format",
            "-of", "json", str(path),
        ]
        completed = subprocess.run(
            command,
            shell=False,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=30,
            check=False,
        )
        if completed.returncode != 0 or len(completed.stdout) > 1024 * 1024:
            raise MediaError("MEDIA_VERIFY_FAILED", "The generated clip did not pass verification.", 500)
        payload = json.loads(completed.stdout)
        streams = payload.get("streams", [])
        video = next((item for item in streams if item.get("codec_type") == "video"), None)
        audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
        duration = float(payload.get("format", {}).get("duration", 0))
        if not video or duration <= 0 or path.stat().st_size <= 0:
            raise MediaError("MEDIA_VERIFY_FAILED", "The generated clip is empty or has no video stream.", 500)
        return {
            "video_codec": str(video.get("codec_name", "unknown")),
            "audio_codec": str(audio.get("codec_name")) if audio else None,
            "duration_seconds": duration,
        }

    def _run(
        self, command: list[str], cancel_requested: Callable[[], bool] | None = None
    ) -> bool:
        process = subprocess.Popen(
            command,
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        started = time.monotonic()
        while process.poll() is None:
            if cancel_requested and cancel_requested():
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
                raise MediaError("JOB_CANCELLED", "Clip generation was cancelled.", 409)
            if time.monotonic() - started > self.total_timeout_seconds:
                process.kill()
                process.wait(timeout=3)
                raise MediaError("MEDIA_TIMEOUT", "FFmpeg exceeded the clip time limit.", 504)
            time.sleep(0.1)
        return process.returncode == 0

    def _safe_output(self, clip_id: str) -> Path:
        if not clip_id.startswith("clip_") or not clip_id.removeprefix("clip_").isalnum():
            raise MediaError("MEDIA_PATH_INVALID", "Clip identity is invalid.", 400)
        path = (self.clip_root / f"{clip_id}.mp4").resolve()
        if path.parent != self.clip_root:
            raise MediaError("MEDIA_PATH_INVALID", "Clip path is outside the clip directory.", 400)
        return path

    @staticmethod
    def _version(path: Path) -> dict[str, object]:
        try:
            completed = subprocess.run(
                [str(path), "-version"], shell=False, stdin=subprocess.DEVNULL,
                capture_output=True, timeout=5, check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return {"available": False, "version": None}
        first_line = completed.stdout.decode("utf-8", errors="replace").splitlines()
        return {
            "available": completed.returncode == 0,
            "version": first_line[0][:200] if first_line else None,
        }


def _with_credentials(locator: str, username: str, password: str) -> str:
    parsed = urlsplit(locator)
    if parsed.scheme not in {"rtsp", "rtsps"} or not parsed.hostname:
        raise MediaError("MEDIA_LOCATOR_INVALID", "NVR playback locator is invalid.", 422)
    if parsed.username is not None or parsed.password is not None:
        raise MediaError("MEDIA_LOCATOR_UNSAFE", "Credential-bearing playback locators are rejected.", 422)
    host = parsed.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    port = f":{parsed.port}" if parsed.port else ""
    netloc = f"{quote(username, safe='')}:{quote(password, safe='')}@{host}{port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))
