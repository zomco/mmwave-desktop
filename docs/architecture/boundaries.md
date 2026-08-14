# Product and repository boundaries

[中文](boundaries_CN.md)

## One product, three modules

Users buy or install TraceCue, not three unrelated products. Internally, modules have independent interfaces so that gateway and engine can later release separately without rewriting desktop.

## mmWave laboratory relationship

| Laboratory repository | Knowledge reused by product | Forbidden coupling |
| --- | --- | --- |
| `mmwave-component` | Protocol knowledge, device transforms, boundary filtering, fixtures | ESPHome/HA runtime dependency |
| `mmwave-card` | Calibration UX, room/zone editor, coordinate convention | Lovelace/HA entity runtime dependency |
| `mmwave-fusion` | Tracking, trajectory quality, `traverse` reasoning, golden exports | Importing the HA integration or its database schema as a product API |

TraceCue may port algorithms with provenance and license review, consume exported `timeline.v1`, and use the Lab for golden validation. It must not add submodules or imports that are required to build/run the product.

## Open-source boundary

ADR-0004 licenses the complete monorepo under MIT. `desktop`, `gateway`, `engine` and integrations therefore share one permissive code license while retaining explicit runtime and data interfaces. Third-party licenses, including FFmpeg's build-dependent LGPL/GPL terms, remain separate distribution obligations.

## Deployment boundary

- NVR-only: desktop can run on demand without gateway.
- Historical sensor timeline: an always-on producer is mandatory; it may be gateway or future capable firmware.
- Multi-radar fusion is expected to require gateway-class compute.
- Cloud relay, remote administration and general LAN exposure are separate future threat models. ADR-0006 permits only an explicit, short-lived, token-scoped read-only share of one generated clip.

## Explicitly rejected or deferred directions

- WeChat Mini Program directly connecting to NVR as the primary path.
- HTTPS cloud JavaScript directly connecting to a private-network NVR.
- Home Assistant as the mainland-market prerequisite.
- A second always-on full recording/transcoding archive.
- A founder-operated nationwide multi-radar installation service.
- Permanent differentiation based only on the same NVR smart-event feed.
- Python video rendering/decoding.

Changing one of these requires an ADR that documents the new evidence, conflict and migration cost.
