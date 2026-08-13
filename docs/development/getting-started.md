# Developer getting started

[中文](getting-started_CN.md)

## Current state

The repository contains an executable 0.1.0 development baseline. Software contracts and synthetic fixtures are testable without hardware; compatibility, codec and installer claims still require authorized hardware and release evidence.

## Prerequisites

- Git 2.40+.
- Python 3.12+ for repository checks and the recommended control plane.
- Node.js LTS only after `desktop/package.json` exists.
- Windows 11 or a supported Windows 10 environment for product smoke tests.
- Access to a dedicated test NVR for hardware work; never use production credentials in fixtures.
- The pinned FFmpeg/FFprobe input for real media tests; run `./packaging/windows/fetch-ffmpeg.ps1`. Binaries remain ignored and are never committed.

## First checkout

```powershell
git clone https://github.com/zomco/tracecue.git
Set-Location tracecue
python scripts/ci/verify_repo.py
python -m pip install -r requirements-dev.lock.txt
python -m pip install --no-build-isolation --no-deps -e ./engine -e ./integrations/hikvision -e ./gateway -e ./desktop/backend
python -m pytest engine/tests integrations/hikvision/tests gateway/tests desktop/backend/tests
npm ci --prefix desktop/frontend
npm test --prefix desktop/frontend
npm run build --prefix desktop/frontend
```

For a local hardware/media run, fetch the pinned tools and start the editable
desktop service from the repository:

```powershell
.\packaging\windows\fetch-ffmpeg.ps1
tracecue-desktop
```

On Windows, an editable checkout automatically discovers the built SPA under
`desktop/frontend/dist` and the verified binaries under
`packaging/windows/tools/`. Build the SPA before launching the service.
`TRACECUE_FRONTEND_DIR` remains available for a nonstandard frontend layout;
`TRACECUE_FFMPEG_PATH` and
`TRACECUE_FFPROBE_PATH` may be set to explicit executable paths when a different
development layout is required. Packaged builds continue to use their adjacent
`frontend/` and `tools/` directories.

Then read, in order:

1. Root README and `AGENTS.md`.
2. Product brief and architecture overview.
3. The README of the module you will change.
4. Relevant specification and ADRs.

## Choosing work

Start from the next incomplete roadmap exit criterion. Prefer a vertical result such as "probe one NVR and store a capability report" over building generic framework layers.

For hardware work, create redacted fixtures and a compatibility record in the same change. For contract work, update English/Chinese docs, JSON schema, examples and tests together.

## Local configuration

Runtime configuration will use an untracked `.env` or user data directory only for development convenience; production secrets belong in Windows-protected storage. Never add real addresses or credentials to `.env.example`.

## Before requesting review

- Rebase/merge current `main` without destroying unrelated work.
- Run repository and module tests.
- Inspect `git diff` for secrets and accidental binary media.
- Update the handoff record if architectural context changed.
- State which hardware/firmware was and was not tested.
