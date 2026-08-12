"""Runtime configuration with loopback-safe defaults."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AppConfig:
    data_dir: Path
    clip_dir: Path
    frontend_dir: Path | None = None
    host: str = "127.0.0.1"
    preferred_port: int = 8765
    ffmpeg_path: Path = Path("ffmpeg")
    ffprobe_path: Path = Path("ffprobe")
    job_poll_seconds: float = 0.25

    @property
    def database_path(self) -> Path:
        return self.data_dir / "tracecue.sqlite"

    @property
    def secret_path(self) -> Path:
        return self.data_dir / "secrets.dpapi.json"

    @classmethod
    def default(cls) -> "AppConfig":
        executable_dir = Path(sys.executable).resolve().parent
        if os.name == "nt":
            local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
            data_dir = local / "TraceCue"
            clip_dir = Path.home() / "Videos" / "TraceCue"
        else:
            data_dir = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "tracecue"
            clip_dir = data_dir / "clips"
        data_dir = Path(os.environ.get("TRACECUE_DATA_DIR", data_dir))
        clip_dir = Path(os.environ.get("TRACECUE_CLIP_DIR", clip_dir))
        frontend_override = os.environ.get("TRACECUE_FRONTEND_DIR")
        bundled_frontend = executable_dir / "frontend"
        frontend_dir = Path(frontend_override) if frontend_override else (bundled_frontend if bundled_frontend.exists() else None)
        bundled_tools = executable_dir / "tools"
        ffmpeg = bundled_tools / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
        ffprobe = bundled_tools / ("ffprobe.exe" if os.name == "nt" else "ffprobe")
        return cls(
            data_dir=data_dir,
            clip_dir=clip_dir,
            frontend_dir=frontend_dir,
            ffmpeg_path=ffmpeg if ffmpeg.exists() else Path("ffmpeg"),
            ffprobe_path=ffprobe if ffprobe.exists() else Path("ffprobe"),
        )

    def prepare(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.clip_dir.mkdir(parents=True, exist_ok=True)
