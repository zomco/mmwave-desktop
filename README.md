# TraceCue

[中文](README_CN.md)

Local-first video retrieval for apartments and small property operators. It connects to an existing NVR, turns event intervals into reviewable bookmarks, and seeks or exports the matching recording. It does not build a second full-video archive.

| Part | What it does | How it runs |
| --- | --- | --- |
| `desktop` | Local web UI, NVR setup, bookmark review, playback, MP4 export | Windows app, started when needed |
| `gateway` | Keeps collecting radar or sensor data and stores high-confidence intervals | Always on, only for sensor-backed installs |
| `engine` | Vendor-neutral intervals, quality gates, `timeline.v1` | Library, not a separate product |

The NVR remains the video store. With only NVR events, TraceCue organizes and exports; it does **not** promise fewer false alarms than the NVR's own smart playback. That difference comes from 2D radar tracks. Runtime does not depend on Home Assistant, Docker, or the mmWave laboratory repositories. The only allowed radar runtime dependency is the `mmwave-engine` package.

This repository has an executable `0.1.0` development baseline. No NVR model or radar model is commercially certified yet. See [implementation status](docs/development/implementation-status.md).

## Quick start

Developer checkout and tests are in [Getting started](docs/development/getting-started.md). After that:

```powershell
python scripts/ci/verify_repo.py
```

There is no end-user installer to point a household at yet. Binary release still needs third-party notices, signing material, and hardware evidence.

## Documentation map

| If you want | Read |
| --- | --- |
| Every document | [Documentation map](docs/README.md) |
| Product intent and non-goals | [Product brief](docs/product/product-brief.md) |
| System shape | [Architecture overview](docs/architecture/overview.md) |
| Developer setup | [Getting started](docs/development/getting-started.md) |
| What is actually implemented | [Implementation status](docs/development/implementation-status.md) |
| Timeline interchange | [timeline.v1](docs/specifications/timeline-v1.md) |
| HTTP API | [HTTP API v1](docs/specifications/http-api-v1.md) |
| Why a radar tag outranks an NVR label | [ADR-0009](docs/architecture/decisions/0009-radar-tag-outranks-nvr.md) |
| Desktop / gateway / cold-archive engine | [desktop](desktop/README.md), [gateway](gateway/README.md), [engine](engine/README.md) |
| AI collaborator rules | [AGENTS.md](AGENTS.md) |

## Radars

TraceCue's high-confidence timeline comes from [mmwave-engine](https://github.com/zomco/mmwave-engine), not from this repository's `engine/` library.

**1D radars cannot use mmwave-fusion**, and they cannot supply a position track to tag video. **2D radars can use every feature**, including fusion and this tag. R60ABD1 also reports height; it is listed with the 2D models because it can be fused.

Figures and progress match [mmwave-component](https://github.com/zomco/mmwave-component/blob/main/README.md). `—` means the manual does not state it. A cell marked *accuracy* is not a range-gate width. LD2410 at 0.20 m resolution reaches 1.6 m. LD2451 reports whole metres. LD2450 and LD2454 publish resolution in each target frame. LD2454's performance table says 8 m; the install section says 6 m tracking.

### 1D radars

| Model | Detection distance | Distance resolution | Progress |
| --- | --- | --- | --- |
| LD2410 | 6 m | 0.75 m / 0.20 m | Developing |
| LD2410B | 6 m | 0.75 m (protocol can also select 0.20 m) | Testing |
| LD2410C | 6 m | 0.75 m (protocol can also select 0.20 m) | Testing |
| LD2411 | 2 m (gesture 1 m) | — | Developing |
| LD2411S | 6 m (micro-motion 3.5 m) | ±5 cm / ±5% (accuracy) | Developing |
| LD2412 | 9 m | 0.75 m | Developing |
| LD2420 | 8 m (micro-motion 6 m) | 0.70 m | Developing |
| LD2450A | 2 m | 0.2 m (sensing accuracy) | Developing |
| LD6002 | 1.5 m (breath / heart) | — | Developing |
| RD-03E | 6 m (micro-motion 3.5 m) | ±5 cm / ±5% (accuracy) | Developing |

### 2D radars

| Model | Detection distance | Angle | Distance resolution | Progress |
| --- | --- | --- | --- | --- |
| LD2450 | 6 m | azimuth ±60°, elevation ±35° | per frame | Developing |
| LD2451 | 100 m | horizontal ±15°, vertical ±7° | 1 m | Testing |
| LD2452 | 6 m | azimuth ±60°, elevation ±30° | 0.72 m | Testing |
| LD2453 | 6 m | azimuth ±40°, elevation ±30° | 0.72 m | Developing |
| LD2454 | 8 m | azimuth ±60°, elevation ±30° | per frame | Testing |
| R60ABD1 | 2.5 m (breath / heart 1.5 m) | ±20° | — | Completed |

## License

TraceCue code is [MIT](LICENSE). Bundled third-party programs keep their own licenses. See [ADR-0004](docs/architecture/decisions/0004-licensing-before-contributions.md).
