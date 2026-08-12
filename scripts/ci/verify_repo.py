"""Validate TraceCue repository contracts without third-party dependencies."""

from __future__ import annotations

import argparse
import json
import re
import sys
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
        if ".git" in relative.parts or ".github" in relative.parts:
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
        if ".git" in relative.parts:
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
        if ".git" not in path.relative_to(ROOT).parts:
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
    excluded_parts = {".git", "node_modules", ".venv", "artifacts"}
    allowed_suffixes = {".md", ".py", ".json", ".yml", ".yaml", ".toml", ".txt"}
    return [
        path
        for path in ROOT.rglob("*")
        if path.is_file()
        and not excluded_parts.intersection(path.relative_to(ROOT).parts)
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
        if path.is_file() and ".git" not in path.relative_to(ROOT).parts:
            if path.suffix.lower() in forbidden_suffixes:
                error(errors, f"forbidden credential file: {path.relative_to(ROOT)}")
    for path in iter_text_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                error(errors, f"possible {label} in {path.relative_to(ROOT)}")


def check_release_readiness(errors: list[str]) -> None:
    required = (
        "packaging/windows/build.ps1",
        "packaging/windows/smoke.ps1",
        "release/manifest.json",
        "release/THIRD_PARTY_NOTICES.txt",
    )
    for relative in required:
        if not (ROOT / relative).exists():
            error(errors, f"release is intentionally blocked; missing {relative}")
    manifest_path = ROOT / "release/manifest.json"
    if manifest_path.exists():
        manifest = load_json(manifest_path, errors)
        if isinstance(manifest, dict):
            for key in ("version", "ffmpeg_version", "artifacts"):
                if not manifest.get(key):
                    error(errors, f"release manifest missing {key}")


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
