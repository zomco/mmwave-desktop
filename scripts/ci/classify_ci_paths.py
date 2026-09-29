"""Classify a TraceCue diff into CI and security job flags.

Fail open: a missing base commit, or a path this file does not recognise,
turns every code job on. Markdown and docs/ do not. repository-contract and
the security audit are not gated here; those workflows always run them.
"""

from __future__ import annotations

import os
import subprocess
import sys

FLAGS = (
    "engine",
    "gateway",
    "hikvision",
    "desktop_backend",
    "desktop_frontend",
    "windows",
    "deps",
    "codeql_py",
    "codeql_js",
)

META = {
    "LICENSE",
    ".gitignore",
    ".gitattributes",
    ".editorconfig",
}


class Flags:
    def __init__(self) -> None:
        self.values = {name: False for name in FLAGS}

    def enable(self, *names: str) -> None:
        for name in names:
            self.values[name] = True

    def all_on(self) -> None:
        self.enable(*FLAGS)


def under(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix + "/")


def is_doc(path: str) -> bool:
    return under(path, "docs") or path.endswith(".md")


def classify(flags: Flags, path: str) -> None:
    if is_doc(path) or path in META:
        return
    if path in {".github/workflows/ci.yml", ".github/workflows/security.yml", "scripts/ci/classify_ci_paths.py"} or under(path, ".github/workflows"):
        flags.all_on()
        return
    if under(path, ".github"):
        return
    matched = False
    if under(path, "engine"):
        flags.enable("engine", "gateway", "desktop_backend", "codeql_py")
        matched = True
    if under(path, "gateway"):
        flags.enable("gateway", "codeql_py")
        matched = True
    if under(path, "integrations/hikvision"):
        flags.enable("hikvision", "desktop_backend", "codeql_py")
        matched = True
    if under(path, "desktop/backend"):
        flags.enable("desktop_backend", "codeql_py")
        matched = True
    if under(path, "desktop/frontend"):
        flags.enable("desktop_frontend", "codeql_js")
        matched = True
    if under(path, "packaging"):
        flags.enable("windows")
        matched = True
    name = path.rsplit("/", 1)[-1]
    if name in {"requirements-dev.lock.txt", "pyproject.toml", "package.json", "package-lock.json"}:
        flags.enable("deps")
        matched = True
        if name in {"requirements-dev.lock.txt", "pyproject.toml"}:
            flags.enable("engine", "gateway", "hikvision", "desktop_backend", "codeql_py")
        if name in {"package.json", "package-lock.json"}:
            flags.enable("desktop_frontend", "codeql_js")
    if path.endswith(".py"):
        flags.enable("codeql_py")
        matched = True
    if path.endswith((".js", ".ts", ".tsx", ".mjs", ".cjs")):
        flags.enable("codeql_js")
        matched = True
    if under(path, "contracts") or under(path, "scripts"):
        matched = True
    if not matched:
        flags.all_on()


def git(args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=check, text=True, capture_output=True)


def have_commit(sha: str) -> bool:
    return git(["git", "cat-file", "-e", f"{sha}^{{commit}}"], check=False).returncode == 0


def ensure_base(sha: str) -> bool:
    if have_commit(sha):
        return True
    git(["git", "fetch", "--filter=blob:none", "--depth=1", "origin", sha], check=False)
    return have_commit(sha)


def write_outputs(flags: Flags) -> None:
    lines = [f"{name}={'true' if flags.values[name] else 'false'}" for name in FLAGS]
    text = "\n".join(lines) + "\n"
    print(text, end="")
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(text)


def main() -> int:
    flags = Flags()
    event = os.environ.get("EVENT_NAME", "")
    before = os.environ.get("EVENT_BEFORE", "")
    pr_base = os.environ.get("PR_BASE", "")

    if event in {"schedule", "workflow_dispatch"}:
        flags.all_on()
        write_outputs(flags)
        return 0
    if event == "pull_request" and pr_base:
        base = pr_base
    elif before and set(before) != {"0"}:
        base = before
    else:
        flags.all_on()
        write_outputs(flags)
        return 0

    if not ensure_base(base):
        flags.all_on()
        write_outputs(flags)
        return 0

    diff = git(["git", "diff", "--name-only", base, "HEAD"], check=False)
    if diff.returncode != 0:
        flags.all_on()
        write_outputs(flags)
        return 0
    for path in diff.stdout.splitlines():
        if path:
            classify(flags, path)
    write_outputs(flags)
    return 0


if __name__ == "__main__":
    sys.exit(main())
