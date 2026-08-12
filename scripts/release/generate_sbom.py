"""Generate a small deterministic CycloneDX SBOM from installed Python and npm locks."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PYTHON_PACKAGES = (
    "tracecue-desktop",
    "tracecue-engine",
    "tracecue-hikvision",
    "fastapi",
    "uvicorn",
    "starlette",
    "pydantic",
)


def python_components() -> list[dict[str, str]]:
    result = []
    for name in PYTHON_PACKAGES:
        distribution = importlib.metadata.distribution(name)
        result.append(
            {
                "type": "library",
                "name": distribution.metadata["Name"],
                "version": distribution.version,
                "purl": f"pkg:pypi/{distribution.metadata['Name'].lower()}@{distribution.version}",
            }
        )
    return result


def npm_components() -> list[dict[str, str]]:
    lock = json.loads((ROOT / "desktop" / "frontend" / "package-lock.json").read_text(encoding="utf-8"))
    result = []
    for location, item in lock.get("packages", {}).items():
        if not location or not location.startswith("node_modules/"):
            continue
        name = location.removeprefix("node_modules/")
        version = item.get("version")
        if version:
            result.append(
                {"type": "library", "name": name, "version": version, "purl": f"pkg:npm/{name}@{version}"}
            )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    components = sorted(python_components() + npm_components(), key=lambda item: item["purl"])
    document = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "metadata": {"component": {"type": "application", "name": "TraceCue", "version": "0.1.0"}},
        "components": components,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

