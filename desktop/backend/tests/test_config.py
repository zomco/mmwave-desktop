from pathlib import Path

from tracecue_desktop.config import AppConfig, _frontend_path


def test_explicit_media_tool_paths_are_used(monkeypatch, tmp_path: Path) -> None:
    ffmpeg = tmp_path / "custom-ffmpeg"
    ffprobe = tmp_path / "custom-ffprobe"
    monkeypatch.setenv("TRACECUE_FFMPEG_PATH", str(ffmpeg))
    monkeypatch.setenv("TRACECUE_FFPROBE_PATH", str(ffprobe))

    config = AppConfig.default()

    assert config.ffmpeg_path == ffmpeg
    assert config.ffprobe_path == ffprobe


def test_editable_checkout_frontend_build_is_discovered(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("TRACECUE_FRONTEND_DIR", raising=False)
    repository_root = tmp_path / "tracecue"
    module_file = (
        repository_root
        / "desktop"
        / "backend"
        / "src"
        / "tracecue_desktop"
        / "config.py"
    )
    frontend = repository_root / "desktop" / "frontend" / "dist"
    frontend.mkdir(parents=True)
    (frontend / "index.html").write_text("<!doctype html>", encoding="utf-8")

    resolved = _frontend_path(tmp_path / "venv" / "Scripts", module_file)

    assert resolved == frontend


def test_frontend_override_takes_precedence(monkeypatch, tmp_path: Path) -> None:
    override = tmp_path / "custom-frontend"
    monkeypatch.setenv("TRACECUE_FRONTEND_DIR", str(override))

    assert _frontend_path(tmp_path / "Scripts") == override
