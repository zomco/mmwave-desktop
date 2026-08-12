"""Validate TraceCue repository contracts without third-party dependencies."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[2]

REQUIRED_PATHS = (
    "README.md",
    "README_CN.md",
    "AGENTS.md",
    "AGENTS_CN.md",
    "CONTRIBUTING.md",
    "CONTRIBUTING_CN.md",
    "SECURITY.md",
    "SECURITY_CN.md",
    "desktop/README.md",
    "desktop/README_CN.md",
    "gateway/README.md",
    "gateway/README_CN.md",
    "engine/README.md",
    "engine/README_CN.md",
    "docs/README.md",
    "docs/README_CN.md",
    "docs/architecture/overview.md",
    "docs/architecture/overview_CN.md",
    "docs/specifications/timeline-v1.md",
    "docs/specifications/timeline-v1_CN.md",
    "contracts/timeline/v1/schema.json",
    "contracts/timeline/v1/examples/minimal.json",
)

MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
EXTERNAL_PREFIXES = ("http://", "https://", "mailto:", "tel:", "#")

SECRET_PATTERNS = {
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "credential URL": re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s/:@]+:[^\s/@]+@", re.I),
}

EXCLUDED_PARTS = {
    ".git",
    ".npm-cache",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "artifacts",
    "build",
    "dist",
    "node_modules",
}


def excluded(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    return bool(EXCLUDED_PARTS.intersection(relative.parts)) or any(
        part.endswith(".egg-info") for part in relative.parts
    )


def error(errors: list[str], message: str) -> None:
    errors.append(message)


def check_required(errors: list[str]) -> None:
    for relative in REQUIRED_PATHS:
        if not (ROOT / relative).exists():
            error(errors, f"missing required path: {relative}")


def paired_path(path: Path) -> Path:
    if path.name.endswith("_CN.md"):
        return path.with_name(path.name.removesuffix("_CN.md") + ".md")
    return path.with_name(path.stem + "_CN.md")


def check_bilingual_pairs(errors: list[str]) -> None:
    for path in ROOT.rglob("*.md"):
        relative = path.relative_to(ROOT)
        if excluded(path) or ".github" in relative.parts:
            continue
        counterpart = paired_path(path)
        if not counterpart.exists():
            error(errors, f"missing bilingual counterpart: {relative} -> {counterpart.relative_to(ROOT)}")


def clean_link_target(raw: str) -> str:
    target = raw.strip().strip("<>")
    if " " in target and not target.startswith(("http://", "https://")):
        target = target.split(" ", 1)[0]
    return unquote(target.split("#", 1)[0])


def check_markdown_links(errors: list[str]) -> None:
    for path in ROOT.rglob("*.md"):
        relative = path.relative_to(ROOT)
        if excluded(path):
            continue
        text = path.read_text(encoding="utf-8")
        for match in MARKDOWN_LINK.finditer(text):
            raw = match.group(1).strip()
            if raw.startswith(EXTERNAL_PREFIXES):
                continue
            target = clean_link_target(raw)
            if not target:
                continue
            resolved = (path.parent / target).resolve()
            try:
                resolved.relative_to(ROOT.resolve())
            except ValueError:
                error(errors, f"link escapes repository: {relative}: {raw}")
                continue
            if not resolved.exists():
                error(errors, f"broken local link: {relative}: {raw}")


def load_json(path: Path, errors: list[str]) -> object | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        error(errors, f"invalid JSON {path.relative_to(ROOT)}: {exc}")
        return None


def parse_timestamp(value: object, label: str, errors: list[str]) -> datetime | None:
    if not isinstance(value, str) or not re.search(r"(?:Z|[+-]\d{2}:\d{2})$", value):
        error(errors, f"{label} must be an RFC 3339 timestamp with explicit offset")
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        error(errors, f"{label} is not a valid timestamp: {value}")
        return None


def check_json_and_timeline(errors: list[str]) -> None:
    for path in ROOT.rglob("*.json"):
        if not excluded(path):
            load_json(path, errors)

    example_path = ROOT / "contracts/timeline/v1/examples/minimal.json"
    example = load_json(example_path, errors)
    if not isinstance(example, dict):
        return
    if example.get("schema_version") != "timeline.v1":
        error(errors, "timeline example schema_version must be timeline.v1")

    for field in ("document_id", "source_id", "generated_at", "producer", "coverage"):
        if field not in example:
            error(errors, f"timeline example missing required field: {field}")
    parse_timestamp(example.get("generated_at"), "generated_at", errors)
    coverage = example.get("coverage")
    if isinstance(coverage, dict):
        coverage_start = parse_timestamp(coverage.get("start_at"), "coverage.start_at", errors)
        coverage_end = parse_timestamp(coverage.get("end_at"), "coverage.end_at", errors)
        if coverage_start and coverage_end and coverage_end <= coverage_start:
            error(errors, "timeline coverage end_at must be after start_at")

    channels = example.get("channels")
    intervals = example.get("intervals")
    if not isinstance(channels, list) or not isinstance(intervals, list):
        error(errors, "timeline example channels and intervals must be arrays")
        return

    channel_ids = [item.get("id") for item in channels if isinstance(item, dict)]
    if len(channel_ids) != len(set(channel_ids)) or None in channel_ids:
        error(errors, "timeline example channel IDs must be present and unique")

    interval_ids: list[object] = []
    for index, item in enumerate(intervals):
        if not isinstance(item, dict):
            error(errors, f"timeline interval {index} must be an object")
            continue
        interval_ids.append(item.get("id"))
        if item.get("channel_id") not in channel_ids:
            error(errors, f"timeline interval {index} references an unknown channel")
        start = parse_timestamp(item.get("start_at"), f"interval {index} start_at", errors)
        end = parse_timestamp(item.get("end_at"), f"interval {index} end_at", errors)
        if start and end and end <= start:
            error(errors, f"timeline interval {index} end_at must be after start_at")
        window = item.get("media_window")
        if isinstance(window, dict):
            media_start = parse_timestamp(
                window.get("start_at"), f"interval {index} media_window.start_at", errors
            )
            media_end = parse_timestamp(
                window.get("end_at"), f"interval {index} media_window.end_at", errors
            )
            if start and media_start and media_start > start:
                error(errors, f"timeline interval {index} media window starts after event")
            if end and media_end and media_end < end:
                error(errors, f"timeline interval {index} media window ends before event")
    if len(interval_ids) != len(set(interval_ids)) or None in interval_ids:
        error(errors, "timeline example interval IDs must be present and unique")


def iter_text_files() -> list[Path]:
    allowed_suffixes = {".md", ".py", ".json", ".yml", ".yaml", ".toml", ".txt"}
    return [
        path
        for path in ROOT.rglob("*")
        if path.is_file()
        and not excluded(path)
        and path.suffix.lower() in allowed_suffixes
    ]


def check_text_hygiene(errors: list[str]) -> None:
    for path in iter_text_files():
        relative = path.relative_to(ROOT)
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            error(errors, f"text file is not UTF-8: {relative}: {exc}")
            continue
        if text and not text.endswith("\n"):
            error(errors, f"text file has no final newline: {relative}")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if line != line.rstrip(" \t"):
                error(errors, f"trailing whitespace: {relative}:{line_number}")


def check_security(errors: list[str]) -> None:
    forbidden_suffixes = {".pfx", ".p12", ".key", ".pem"}
    for path in ROOT.rglob("*"):
        if path.is_file() and not excluded(path):
            if path.suffix.lower() in forbidden_suffixes:
                error(errors, f"forbidden credential file: {path.relative_to(ROOT)}")
    for path in iter_text_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                error(errors, f"possible {label} in {path.relative_to(ROOT)}")


def check_license_and_release_metadata(errors: list[str]) -> None:
    license_path = ROOT / "LICENSE"
    if not license_path.exists() or not license_path.read_text(encoding="utf-8").startswith("MIT License\n"):
        error(errors, "root LICENSE must contain the accepted MIT License")
    for relative in (
        "engine/pyproject.toml",
        "gateway/pyproject.toml",
        "integrations/hikvision/pyproject.toml",
        "desktop/backend/pyproject.toml",
    ):
        path = ROOT / relative
        try:
            project = tomllib.loads(path.read_text(encoding="utf-8"))["project"]
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError, KeyError) as exc:
            error(errors, f"invalid package metadata {relative}: {exc}")
            continue
        license_value = project.get("license")
        if license_value not in ("MIT", {"text": "MIT"}):
            error(errors, f"package metadata must declare MIT: {relative}")

    manifest_path = ROOT / "release/manifest.json"
    manifest = load_json(manifest_path, errors)
    if not isinstance(manifest, dict):
        return
    required = (
        "version", "project_license", "license_decision", "ffmpeg_distribution",
        "ffmpeg_license", "ffmpeg_version", "ffmpeg_release_tag", "ffmpeg_archive_url",
        "ffmpeg_archive_sha256", "ffmpeg_source_url", "ffmpeg_source_commit",
        "ffmpeg_source_sha256", "ffmpeg_build_source_url", "ffmpeg_build_source_commit",
        "ffmpeg_build_source_sha256", "ffmpeg_gpl_license_url",
        "ffmpeg_gpl_license_sha256", "ffmpeg_lgpl_license_url",
        "ffmpeg_lgpl_license_sha256", "ffmpeg_sha256", "ffprobe_sha256",
        "ffmpeg_h264_encoder", "release_blockers", "artifacts",
    )
    for key in required:
        if not manifest.get(key):
            error(errors, f"release manifest missing {key}")
    if manifest.get("project_license") != "MIT":
        error(errors, "release manifest project_license must be MIT")
    if manifest.get("ffmpeg_license") != "LGPL-3.0-or-later":
        error(errors, "release manifest must pin the selected LGPL-3.0-or-later FFmpeg build")
    if manifest.get("ffmpeg_h264_encoder") != "libopenh264":
        error(errors, "release manifest must match the packaged H.264 fallback encoder")
    release_tag = manifest.get("ffmpeg_release_tag")
    archive_url = manifest.get("ffmpeg_archive_url")
    if release_tag == "latest" or (isinstance(archive_url, str) and "/latest/" in archive_url):
        error(errors, "FFmpeg release metadata must not use a floating latest reference")
    if isinstance(release_tag, str) and isinstance(archive_url, str) and release_tag not in archive_url:
        error(errors, "FFmpeg archive URL must contain the pinned release tag")
    for key in (
        "ffmpeg_archive_sha256", "ffmpeg_source_sha256", "ffmpeg_build_source_sha256",
        "ffmpeg_gpl_license_sha256", "ffmpeg_lgpl_license_sha256", "ffmpeg_sha256",
        "ffprobe_sha256",
    ):
        value = manifest.get(key)
        if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
            error(errors, f"release manifest {key} must be a lowercase SHA-256")
    for key in ("ffmpeg_source_commit", "ffmpeg_build_source_commit"):
        value = manifest.get(key)
        if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{40}", value) is None:
            error(errors, f"release manifest {key} must be a full commit SHA")


def check_release_readiness(errors: list[str]) -> None:
    required = (
        "packaging/windows/build.ps1",
        "packaging/windows/fetch-ffmpeg.ps1",
        "packaging/windows/smoke.ps1",
        "packaging/windows/tracecue.spec",
        "packaging/windows/TraceCue.iss",
        "release/manifest.json",
        "release/THIRD_PARTY_NOTICES.txt",
        "scripts/release/generate_sbom.py",
    )
    for relative in required:
        if not (ROOT / relative).exists():
            error(errors, f"release is intentionally blocked; missing {relative}")
    manifest_path = ROOT / "release/manifest.json"
    if manifest_path.exists():
        manifest = load_json(manifest_path, errors)
        if isinstance(manifest, dict):
            if manifest.get("release_ready") is not True:
                error(errors, "release manifest has not been approved (release_ready must be true)")
            if manifest.get("release_blockers"):
                error(errors, "release manifest still lists unresolved release_blockers")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--security", action="store_true", help="run secret/path audit")
    parser.add_argument("--release", action="store_true", help="enforce release readiness gates")
    args = parser.parse_args()

    errors: list[str] = []
    check_required(errors)
    check_bilingual_pairs(errors)
    check_markdown_links(errors)
    check_json_and_timeline(errors)
    check_text_hygiene(errors)
    check_license_and_release_metadata(errors)
    if args.security:
        check_security(errors)
    if args.release:
        check_release_readiness(errors)

    if errors:
        print("TraceCue repository verification failed:", file=sys.stderr)
        for item in errors:
            print(f"- {item}", file=sys.stderr)
        return 1
    modes = ["contracts"]
    if args.security:
        modes.append("security")
    if args.release:
        modes.append("release")
    print(f"TraceCue repository verification passed ({', '.join(modes)}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
