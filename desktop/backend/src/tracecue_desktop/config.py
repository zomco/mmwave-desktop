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
    vision_model_path: Path | None = None
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
        frontend_dir = _frontend_path(executable_dir)
        ffmpeg = _media_tool_path("ffmpeg", executable_dir)
        ffprobe = _media_tool_path("ffprobe", executable_dir)
        vision_model = _vision_model_path(executable_dir)
        return cls(
            data_dir=data_dir,
            clip_dir=clip_dir,
            frontend_dir=frontend_dir,
            ffmpeg_path=ffmpeg,
            ffprobe_path=ffprobe,
            vision_model_path=vision_model,
        )

    def prepare(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.clip_dir.mkdir(parents=True, exist_ok=True)


def _media_tool_path(name: str, executable_dir: Path) -> Path:
    """Resolve packaged, explicitly configured, or checkout-local media tools."""
    executable_name = f"{name}.exe" if os.name == "nt" else name
    override = os.environ.get(f"TRACECUE_{name.upper()}_PATH")
    if override:
        return Path(override)

    candidates = [executable_dir / "tools" / executable_name]
    if os.name == "nt":
        # Editable installs run from the repository venv, while the verified
        # binaries fetched by packaging/windows/fetch-ffmpeg.ps1 live here.
        repository_root = Path(__file__).resolve().parents[4]
        candidates.append(repository_root / "packaging" / "windows" / "tools" / executable_name)
    return next((candidate for candidate in candidates if candidate.is_file()), Path(name))


def _frontend_path(executable_dir: Path, module_file: Path | None = None) -> Path | None:
    """Resolve an override, packaged SPA, or editable-checkout SPA build."""
    override = os.environ.get("TRACECUE_FRONTEND_DIR")
    if override:
        return Path(override)

    module_path = (module_file or Path(__file__)).resolve()
    candidates = [executable_dir / "frontend"]
    if len(module_path.parents) > 4:
        repository_root = module_path.parents[4]
        candidates.append(repository_root / "desktop" / "frontend" / "dist")
    return next(
        (candidate for candidate in candidates if (candidate / "index.html").is_file()),
        None,
    )


def _vision_model_path(executable_dir: Path) -> Path | None:
    override = os.environ.get("TRACECUE_VISION_MODEL_PATH")
    if override:
        return Path(override)
    candidates = [executable_dir / "models" / "yolox_nano.onnx"]
    module_path = Path(__file__).resolve()
    if len(module_path.parents) > 4:
        repository_root = module_path.parents[4]
        candidates.append(repository_root / "packaging" / "windows" / "models" / "yolox_nano.onnx")
    return next((candidate for candidate in candidates if candidate.is_file()), None)
