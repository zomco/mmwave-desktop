# TraceCue Desktop

[中文](README_CN.md)

Desktop is the primary user-facing application: a Windows process serving a same-origin SPA and HTTP API on loopback.

## Owns

- NVR onboarding, capability evidence and channel aliases.
- Event-first recording search, saved area/channel/type filters and timeline import/mapping.
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

The backend implements the HTTP API v1 routes, SQLite migrations v1-v6, DPAPI credential references, bounded ONVIF/private-subnet discovery, evidence-backed NVR onboarding, on-demand NVR/camera device-detail reads, per-camera ordinary/Smart event-rule audits with endpoint-normalized image overlays, bounded historical alarm-log search with start/stop duration pairing, cached camera-identification snapshots (low stream first, recent recording fallback), saved single-camera/single-event filters, persistent Trace sessions and review state, event-span timeline and dynamic duration facets, cached JPEG/WebP event previews, phase-progress media jobs, timeline imports/mapping, FFmpeg remux/transcode/verify, exact-event-window atomic clips with event/search provenance, quota retention and bounded Range delivery. The React/Tailwind SPA keeps four primary views: event search, device center, candidates/exports and settings. Event search requires one camera, one event type and a time range; it refreshes camera images once when the page opens, overlays the selected event rule on the selected camera, renders all events on one zoomable track and loads event images only after a timeline range/event or all-events secondary choice. Generated clips can be downloaded with byte progress or explicitly shared through a 15-minute token-scoped LAN QR page while the main API remains on loopback. Continuous recording files are media sources, not event results. Timeline comparison/mapping remains an advanced later-stage surface.

```powershell
python -m pip install -r requirements-dev.lock.txt
python -m pip install --no-build-isolation --no-deps -e ./engine -e ./integrations/hikvision -e ./desktop/backend
python -m pytest desktop/backend/tests
npm ci --prefix desktop/frontend
npm test --prefix desktop/frontend
npm run build --prefix desktop/frontend
```

Real NVR authentication/search/media behavior and FFmpeg codec outcomes remain hardware tests, not CI claims.
