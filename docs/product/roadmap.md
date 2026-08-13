# Roadmap

[中文](roadmap_CN.md)

The roadmap is organized by evidence-producing vertical slices, not feature count. Dates are deliberately omitted until the first hardware matrix is available.

Software implementation status is tracked separately from hardware/product exit evidence. As of the 0.1.0 development baseline, the M1-M5 software paths exist, but their hardware, release and labelled-data exit criteria below remain open. See the [implementation status](../development/implementation-status.md).

## M0 — Repository and contracts

- Product, architecture, security and AI collaboration baseline.
- `timeline.v1` schema plus examples.
- CI that validates repository contracts and bilingual documentation.
- Exit: a new collaborator can identify scope, boundaries and next work without chat history.

## M1 — Hikvision protocol spike

- Read-only compatibility probe.
- Digest authentication, device identity, clock skew and channel discovery.
- Recording search pagination and redacted response fixtures.
- Media resolver proves one channel/time window can produce an RTSP input.
- Exit: two target NVR model/firmware combinations have evidence-backed capability reports.

## M2 — H.264 clip vertical slice

- One NVR, one channel, one date range.
- Persisted job state and a short MP4 via FFmpeg remux.
- Local browser playback and explicit recording-gap errors.
- Exit: golden H.264 clips meet the initial playback latency target.

## M3 — Distributable NVR foundation

- LAN discovery, multi-channel/area/event filters, saved filters, event previews, rule/notification audits, event-linked exports, H.265/audio compatibility path and diagnostics bundle.
- Windows one-folder installer, signing pipeline and data retention controls.
- Exit: an unfamiliar tester completes install-to-playback from written instructions.

## M4 — Timeline golden path

- Inspect/map/commit `timeline.v1` imports.
- High-confidence versus NVR-source comparison UI.
- Review-volume, precision, recall and find-time measurement.
- Exit: a labelled dataset supports or rejects the differentiation hypothesis.

## M5 — Always-on gateway

- HA-free radar ingestion for one certified device/model.
- Clock health, short trajectory buffer, quality gate and durable intervals.
- Automatic discovery/import by desktop.
- Exit: an unattended deployment retains correct historical bookmarks across desktop shutdowns.

## Deferred

LAN exposure, continuous live streaming preview, ONVIF brand expansion, direct phone relay, cloud relay, automatic updater, channel licensing and hardware bundles remain deferred until preceding evidence exists. Multiple NVR records and bounded cross-NVR aggregate search are implemented.
