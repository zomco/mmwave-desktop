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
| M2 H.264 clip | Implemented | persistent jobs, resolver, FFmpeg argument arrays, `.partial`/FFprobe/atomic path, Range tests with fake media | Blocked on pinned FFmpeg distribution and real H.264 NVR P95 result |
| M3 distributable foundation | Substantially implemented | multi-channel/aliases, H.265 fallback, quota, diagnostics/status, one-folder/installer/sign/SBOM/smoke scripts | Blocked on ADR-0004, FFmpeg hashes/notices, certificate, built installer and unfamiliar-user test |
| M4 timeline path | Implemented | strict inspect/commit/hash/idempotency, mapping/correction, quality/source UI, comparison guardrail tests | Blocked on a cleared labelled golden dataset and measured recall/precision/find-time |
| M5 gateway | Core implemented | bounded experimental input, reconnect, clock health, track quality, SQLite durability, export tests while Desktop is offline | Blocked on selecting/certifying one physical radar model and unattended deployment evidence |

## Implemented product surface

- Engine: value types, strict 8 MiB `timeline.v1`, RFC 3339 offset rules, deterministic identity, quality gate, media window, merge/filter and idempotent upsert.
- Hikvision: Digest HTTP(S), evidence snapshots, defensive XML, channels, recording pages, locators and coverage gaps.
- Desktop backend: loopback service, same-origin safety, SQLite migration v1, DPAPI references, HTTP API v1, jobs/recovery/cancel, bookmark index, timeline mapping, clips, quota and bounded Range.
- Desktop frontend: add/probe device, search, honest NVR candidates, high-confidence queue, clip playback, timeline import/mapping, comparison and diagnostics.
- Gateway: HA-free experimental bridge, clock health, bounded trajectory buffer, traverse quality, durable intervals and export.
- Delivery: exact npm lock, Python development lock, module CI, CodeQL, Dependabot, Windows packaging/sign/install/smoke and release manifest gates.

## External evidence still required

1. The owner must decide the repository/product license and supersede ADR-0004 before publishing a binary.
2. Select a verifiable LGPL FFmpeg/FFprobe build, record source/version/hashes and exact notices, then place tools only in the packaging input outside Git history if redistribution terms permit.
3. Run the compatibility procedure on two authorized Hikvision model/firmware combinations, save redacted fixtures/evidence and measure H.264/H.265/audio outcomes.
4. Select one legally/protocol-reviewed radar adapter, capture synthetic/redacted fixtures and run an unattended clock/reconnect/offline-retention scenario.
5. Run the signed installer smoke test and an unfamiliar-user install-to-playback session.
6. Create or obtain a cleared labelled dataset before reporting precision, recall or review-volume improvement.

## Next smallest executable step

Resolve ADR-0004, then run the read-only probe against the first owner-controlled Hikvision NVR and commit its redacted compatibility evidence. That result determines whether media and packaging hardware gates can proceed without redesign.

