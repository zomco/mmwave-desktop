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
        total_timeout_seconds: int = 1_800,
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
        max_duration_seconds: float | None = None,
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
                metadata = self._render_compatible_input(
                    playback_locators[0], username, password, partial, audio_policy,
                    cancel_requested, max_duration_seconds=max_duration_seconds,
                )
            else:
                for index, locator in enumerate(playback_locators):
                    segment = self.clip_root / f".{clip_id}.segment-{index}.mp4"
                    segment_partial = segment.with_suffix(segment.suffix + ".partial")
                    self._render_compatible_input(
                        locator, username, password, segment_partial, audio_policy,
                        cancel_requested, max_duration_seconds=max_duration_seconds,
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

    def generate_preview(
        self,
        *,
        preview_id: str,
        playback_locator: str,
        username: str,
        password: str,
        cancel_requested: Callable[[], bool] | None = None,
    ) -> Path:
        return self._generate_jpeg(
            media_id=preview_id,
            required_prefix="preview_",
            directory="previews",
            playback_locator=playback_locator,
            username=username,
            password=password,
            cancel_requested=cancel_requested,
        )

    def generate_snapshot(
        self,
        *,
        snapshot_id: str,
        live_locator: str,
        username: str,
        password: str,
        cancel_requested: Callable[[], bool] | None = None,
    ) -> Path:
        return self._generate_jpeg(
            media_id=snapshot_id,
            required_prefix="snapshot_",
            directory="snapshots",
            playback_locator=live_locator,
            username=username,
            password=password,
            cancel_requested=cancel_requested,
        )

    def generate_animation(
        self,
        *,
        animation_id: str,
        playback_locator: str,
        username: str,
        password: str,
        duration_seconds: float = 3,
        cancel_requested: Callable[[], bool] | None = None,
    ) -> Path:
        if not animation_id.startswith("animation_") or not animation_id.removeprefix("animation_").isalnum():
            raise MediaError("MEDIA_PATH_INVALID", "Animation identity is invalid.", 400)
        animation_root = (self.clip_root / "animations").resolve()
        animation_root.mkdir(parents=True, exist_ok=True)
        output = (animation_root / f"{animation_id}.webp").resolve()
        partial = output.with_suffix(".webp.partial")
        authenticated = _with_credentials(playback_locator, username, password)
        command = [
            str(self.ffmpeg_path), "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
            "-rtsp_transport", "tcp", "-timeout", str(self.connection_timeout_seconds * 1_000_000),
            "-i", authenticated, "-map", "0:v:0", "-t", f"{max(1, min(duration_seconds, 5)):g}",
            "-vf", "fps=4,scale=480:-2:force_original_aspect_ratio=decrease",
            "-an", "-loop", "0", "-c:v", "libwebp_anim", "-quality", "60",
            "-f", "webp", str(partial),
        ]
        try:
            if not self._run(command, cancel_requested):
                raise MediaError("MEDIA_ANIMATION_FAILED", "The event hover preview could not be generated.", 422)
            size = partial.stat().st_size
            header = partial.read_bytes()[:12]
            if size <= 12 or size > 20 * 1024 * 1024 or header[:4] != b"RIFF" or header[8:12] != b"WEBP":
                raise MediaError("MEDIA_ANIMATION_FAILED", "The generated hover preview is not valid WebP.", 500)
            partial.replace(output)
            return output
        finally:
            partial.unlink(missing_ok=True)

    def _generate_jpeg(
        self,
        *,
        media_id: str,
        required_prefix: str,
        directory: str,
        playback_locator: str,
        username: str,
        password: str,
        cancel_requested: Callable[[], bool] | None,
    ) -> Path:
        if not media_id.startswith(required_prefix) or not media_id.removeprefix(required_prefix).isalnum():
            raise MediaError("MEDIA_PATH_INVALID", "Preview identity is invalid.", 400)
        preview_root = (self.clip_root / directory).resolve()
        preview_root.mkdir(parents=True, exist_ok=True)
        output = (preview_root / f"{media_id}.jpg").resolve()
        partial = output.with_suffix(".jpg.partial")
        authenticated = _with_credentials(playback_locator, username, password)
        command = [
            str(self.ffmpeg_path), "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
            "-rtsp_transport", "tcp", "-timeout", str(self.connection_timeout_seconds * 1_000_000),
            "-i", authenticated, "-map", "0:v:0", "-frames:v", "1",
            "-q:v", "4", "-f", "image2", str(partial),
        ]
        try:
            if not self._run(command, cancel_requested):
                raise MediaError("MEDIA_PREVIEW_FAILED", "The preview image could not be generated.", 422)
            size = partial.stat().st_size
            if size <= 4 or size > 20 * 1024 * 1024 or partial.read_bytes()[:3] != b"\xff\xd8\xff":
                raise MediaError("MEDIA_PREVIEW_FAILED", "The generated preview is not a valid JPEG.", 500)
            partial.replace(output)
            return output
        finally:
            partial.unlink(missing_ok=True)

    def _render_compatible_input(
        self,
        locator: str,
        username: str,
        password: str,
        output: Path,
        audio_policy: str,
        cancel_requested: Callable[[], bool] | None,
        *,
        max_duration_seconds: float | None = None,
    ) -> dict[str, object]:
        source_codec = self._probe_video_codec(locator, username, password)
        self._render_input(
            locator, username, password, output, audio_policy, cancel_requested,
            force_h264=source_codec != "h264", max_duration_seconds=max_duration_seconds,
        )
        metadata = self._verify(output)
        if metadata["video_codec"] != "h264":
            raise MediaError("MEDIA_CODEC_UNSUPPORTED", "The recording could not be converted to H.264.", 422)
        return metadata

    def _probe_video_codec(self, locator: str, username: str, password: str) -> str:
        authenticated = _with_credentials(locator, username, password)
        command = [
            str(self.ffprobe_path), "-v", "error", "-rtsp_transport", "tcp",
            "-timeout", str(self.connection_timeout_seconds * 1_000_000),
            "-select_streams", "v:0", "-show_entries", "stream=codec_name",
            "-of", "json", authenticated,
        ]
        try:
            completed = subprocess.run(
                command,
                shell=False,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise MediaError("MEDIA_PROBE_FAILED", "The NVR recording stream could not be inspected.", 502) from exc
        if completed.returncode != 0 or len(completed.stdout) > 1024 * 1024:
            raise MediaError("MEDIA_PROBE_FAILED", "The NVR recording stream could not be inspected.", 502)
        try:
            payload = json.loads(completed.stdout)
            codec = str(payload["streams"][0]["codec_name"]).lower()
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise MediaError("MEDIA_PROBE_FAILED", "The NVR recording has no identifiable video stream.", 422) from exc
        return codec

    def _render_input(
        self,
        locator: str,
        username: str,
        password: str,
        output: Path,
        audio_policy: str,
        cancel_requested: Callable[[], bool] | None,
        *,
        force_h264: bool = False,
        max_duration_seconds: float | None = None,
    ) -> None:
        authenticated = _with_credentials(locator, username, password)
        audio_attempts = {
            # Some NVRs advertise a private audio payload that FFmpeg reports as
            # an audio stream but cannot decode. "prefer" may safely fall back
            # to video-only output; "preserve" remains strict.
            "prefer": [["-c:a", "aac", "-b:a", "128k"], ["-an"]],
            "preserve": [["-c:a", "copy"]],
            "omit": [["-an"]],
        }[audio_policy]
        common = [
            str(self.ffmpeg_path), "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
            "-rtsp_transport", "tcp", "-timeout", str(self.connection_timeout_seconds * 1_000_000),
            "-i", authenticated,
        ]
        video_args = list(H264_COMPATIBILITY_ARGS) if force_h264 else ["-c:v", "copy"]
        for audio_args in audio_attempts:
            duration_args = ["-t", f"{max_duration_seconds:g}"] if max_duration_seconds else []
            command = common + ["-map", "0:v:0", "-map", "0:a?", *duration_args, *video_args, *audio_args,
                "-movflags", "+faststart", "-f", "mp4", str(output)]
            if self._run(command, cancel_requested):
                return
        if not force_h264:
            self._render_input(
                locator, username, password, output, audio_policy, cancel_requested,
                force_h264=True, max_duration_seconds=max_duration_seconds,
            )
            return
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
