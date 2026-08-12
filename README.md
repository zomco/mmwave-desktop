# TraceCue

[中文](README_CN.md)

TraceCue is a local-first video retrieval product for apartments and small property operators. It connects to an existing NVR, turns event intervals into reviewable bookmarks, and seeks or exports the corresponding recording without building a second full-video archive.

The product is intentionally split into three internal parts while remaining one repository and one product family:

| Part | Responsibility | Runtime shape |
| --- | --- | --- |
| `desktop` | Local Web UI, NVR management, bookmark review, playback and MP4 export | On-demand Windows application |
| `gateway` | Continuous radar/sensor collection and durable high-confidence intervals | Always-on companion for sensor-backed deployments |
| `engine` | Vendor-neutral interval model, quality gates, merge/filter rules and `timeline.v1` | Embedded library, not a separate end-user product |

## Product boundary

The NVR remains the authoritative video store. TraceCue indexes metadata bookmarks and resolves media on demand. It does not continuously ingest or transcode all NVR recordings.

The first delivery slice uses Hikvision ISAPI and RTSP. With only NVR-originated events, TraceCue improves organization and export workflow but does **not** promise materially lower false positives than Hikvision's native smart playback. Differentiation comes from later high-confidence timelines such as mmWave trajectories.

TraceCue is independent from `mmwave-component`, `mmwave-card`, `mmwave-fusion`, Home Assistant and Docker at runtime. Those repositories remain a laboratory and technical reference, not product dependencies.

## Repository status

This repository currently contains the product, architecture and delivery contracts needed to begin implementation. Executable product code has not yet landed. See the [roadmap](docs/product/roadmap.md) and [documentation map](docs/README.md).

## Start here

- Product intent and constraints: [Product brief](docs/product/product-brief.md)
- System shape and boundaries: [Architecture overview](docs/architecture/overview.md)
- Developer onboarding: [Getting started](docs/development/getting-started.md)
- AI collaborator instructions: [AGENTS.md](AGENTS.md)
- Timeline interchange: [timeline.v1 specification](docs/specifications/timeline-v1.md)
- CI/CD and release gates: [CI/CD](docs/operations/ci-cd.md)

## License notice

The repository was initialized with GPL-3.0. The intended commercial/open-source boundary has not yet been reconciled with that choice. Do not accept external code contributions or copy third-party code into product modules until [ADR-0004](docs/architecture/decisions/0004-licensing-before-contributions.md) is resolved.
