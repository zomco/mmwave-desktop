# ADR-0008: Local clips are the primary review path

[中文](0008-local-clip-review_CN.md)

- Status: Accepted
- Date: 2026-09-27
- Supersedes: the primary-path conclusion of [ADR-0003](0003-nvr-authoritative-media.md)

## Context

Apartment operators scrub recordings after a vague report. Seeking a box NVR timeline is slow even in the vendor client. mmWave fusion already decides when and where a person-like track happened. That index is useful only if the still or short clip opens immediately.

ADR-0003 correctly rejected a second full-time video archive. It does not require every review to seek the NVR.

## Decision

1. The always-on service is the product runtime. Closing the review UI must not drop radar history.
2. Primary review media is a still and a short clip cut from the live camera stream when an `enter`, `dwell`, or `traverse` event fires. Files stay on local disk.
3. The NVR remains an optional cold archive. ISAPI search and export stay available, but they are not the default review path and must be labelled as possibly slow.
4. Tracking, zone events, and trajectory scores come from the `mmwave-engine` package (`mmwave_engine`). Home Assistant and the `mmwave-fusion` integration are not runtime dependencies.
5. Range-only or presence-only sensors may gate a light. They do not enter fusion tracks.
6. The service binds to `127.0.0.1` unless a later ADR says otherwise. Windows, macOS, and Linux LTS run it as a background service. Signed installers are not required for this decision.

## Consequences

NVR-only deployments no longer claim lower false positives. A site without a live RTSP camera still gets radar events, but no playable still. `mmwave-engine` must be installed or present beside this repository for the fusion review loop.
