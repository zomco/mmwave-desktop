# TraceCue Desktop

[中文](README_CN.md)

Desktop is the primary user-facing application: a Windows process serving a same-origin SPA and HTTP API on loopback.

## Owns

- NVR onboarding, capability evidence and channel aliases.
- Bookmark search and timeline import/mapping.
- Recording coverage resolution through adapters.
- Persistent background jobs and FFmpeg clip generation.
- SQLite migrations, local clip quota and support diagnostics.

## Does not own

- Continuous sensor collection while the application is closed.
- Radar protocol/fusion algorithms.
- A second full recording archive.
- Cloud or LAN remote access in MVP.

## Initial implementation recommendation

The executable baseline uses Python 3.12/FastAPI, React/TypeScript/Vite, SQLite, FFmpeg/FFprobe subprocesses and a one-folder Windows package. ADR-0005 remains proposed until hosted Windows/Linux CI and packaging evidence satisfy all acceptance conditions.

## Contract dependencies

Desktop may depend on `engine` and `integrations/hikvision`. It consumes `timeline.v1`; it must not read gateway storage directly. Public routes follow the HTTP API v1 draft.

## First executable slice

One supported NVR, one channel and one time window produce an H.264 MP4 that plays in the browser, with explicit authentication, clock and recording-gap diagnostics.

## Implemented baseline

The backend implements the HTTP API v1 routes, SQLite migration v1, DPAPI credential references, evidence-backed NVR onboarding, channel aliases, persistent searches/jobs, bookmark review, inspect/commit timeline imports, source-to-space-to-camera mapping, FFmpeg remux/transcode/verify, atomic clips, quota retention and bounded Range delivery. The SPA implements the first-run, review, device, source/mapping, comparison, clip and diagnostics views.

```powershell
python -m pip install -r requirements-dev.lock.txt
python -m pip install --no-build-isolation --no-deps -e ./engine -e ./integrations/hikvision -e ./desktop/backend
python -m pytest desktop/backend/tests
npm ci --prefix desktop/frontend
npm test --prefix desktop/frontend
npm run build --prefix desktop/frontend
```

Real NVR authentication/search/media behavior and FFmpeg codec outcomes remain hardware tests, not CI claims.
