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

Python 3.12/FastAPI control plane, React/TypeScript/Vite SPA, SQLite, FFmpeg/FFprobe subprocesses and a one-folder Windows package. This is a recommendation until an implementation ADR is accepted.

## Contract dependencies

Desktop may depend on `engine` and `integrations/hikvision`. It consumes `timeline.v1`; it must not read gateway storage directly. Public routes follow the HTTP API v1 draft.

## First executable slice

One supported NVR, one channel and one time window produce an H.264 MP4 that plays in the browser, with explicit authentication, clock and recording-gap diagnostics.
