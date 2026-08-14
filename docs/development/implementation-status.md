# Implementation status

[中文](implementation-status_CN.md)

This is the evidence-backed status of the `0.1.0` development baseline. "Implemented" means exercised by local/fixture tests; it does not upgrade an untested hardware combination to supported.

## Baseline found on 2026-08-12

Before this implementation, the repository contained M0 documentation, contracts and repository checks only. There were no module manifests or executable product sources. M1-M5 were specifications rather than code.

## Current completion by slice

| Slice | Software implementation | Evidence available | Exit criterion state |
| --- | --- | --- | --- |
| M0 contracts | Complete | repository and security verifier | Complete |
| M1 Hikvision probe | Implemented | synthetic device/time/channel/search fixtures; auth/size/XML/pagination failure tests | Blocked on two authorized NVR model/firmware evidence records |
| M2 H.264 clip | Implemented | persistent jobs, resolver, FFmpeg argument arrays, `.partial`/FFprobe/atomic path, Range tests and pinned `libopenh264` smoke | Blocked on real H.264 NVR P95 result |
| M3 distributable foundation | Substantially implemented | MIT decision; pinned FFmpeg binary/source hashes; multi-channel/aliases, LAN discovery, event-rule audit, saved filters, previews, event-linked exports, H.265 fallback, quota, diagnostics/status, one-folder/installer/sign/SBOM/smoke scripts | Blocked on complete static-dependency source/notices review, certificate, built installer and unfamiliar-user test |
| M4 timeline path | Implemented | strict inspect/commit/hash/idempotency, mapping/correction, quality/source UI, comparison guardrail tests | Blocked on a cleared labelled golden dataset and measured recall/precision/find-time |
| M5 gateway | Core implemented | bounded experimental input, reconnect, clock health, track quality, SQLite durability, export tests while Desktop is offline | Blocked on selecting/certifying one physical radar model and unattended deployment evidence |

## Implemented product surface

- Engine: value types, strict 8 MiB `timeline.v1`, RFC 3339 offset rules, deterministic identity, quality gate, media window, merge/filter and idempotent upsert.
- Hikvision: Digest HTTP(S), evidence snapshots, defensive XML, channels, on-demand device details, ordinary/Smart rule overlays, historical alarm-log pages, recording pages, locators and coverage gaps.
- Desktop backend: loopback service, same-origin safety, SQLite migrations v1-v5, DPAPI references, HTTP API v1, bounded discovery, per-camera ordinary/Smart rule capability and overlays, bounded historical alarm-log search, expiring camera-identification snapshots with recent-recording fallback, single-camera/single-event filters, persistent Trace sessions with review state and bounded event-span timelines, cached JPEG/WebP previews, adjacent-event-aware clip jobs, recovery/cancel, timeline mapping, quota and bounded Range.
- Desktop frontend: React/Tailwind event-first search, automatic/manual device onboarding, on-demand device details, combined camera/rule cards, ordinary/Smart grouping, capability-aware camera filtering, NVR-grouped visual target selection, single localized behavior without continuous/catch-all event filters, zoomable/clickable/drag-select event timeline, dynamic duration facets, automatic paged previews with hover motion, event-linked clip playback/download and local diagnostics. Timeline mapping/comparison is deferred from primary navigation.
- Gateway: HA-free experimental bridge, clock health, bounded trajectory buffer, traverse quality, durable intervals and export.
- Delivery: exact npm lock, Python development lock, module CI, CodeQL, Dependabot, Windows packaging/sign/install/smoke and release manifest gates.

## External evidence still required

1. Mirror and review the complete corresponding source and notices for the pinned BtbN static LGPL dependency set; the FFmpeg and build-script snapshots are already pinned.
2. Grant live-view permission to a dedicated read-only account on the authorized `DS-7808NB-K1/8P` if true near-live identification is required, then repeat the probe/search/rule/export procedure on a second Hikvision model/firmware combination. Save only redacted fixtures/evidence and measure H.264/H.265/audio outcomes.
3. Select one legally/protocol-reviewed radar adapter, capture synthetic/redacted fixtures and run an unattended clock/reconnect/offline-retention scenario.
4. Configure approved signing credentials, then run the signed installer smoke test and an unfamiliar-user install-to-playback session.
5. Create or obtain a cleared labelled dataset before reporting precision, recall or review-volume improvement.

## Next smallest executable step

Run `packaging/windows/fetch-ffmpeg.ps1 -IncludeSourceSnapshots`, review the resulting build configuration/source inputs, then run the read-only probe against the first owner-controlled Hikvision NVR and commit its redacted compatibility evidence.
