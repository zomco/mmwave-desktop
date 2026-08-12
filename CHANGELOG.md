# Changelog

[中文](CHANGELOG_CN.md)

All notable changes will be documented here after the first implementation milestone. Releases follow Semantic Versioning once a public API or distributable application exists.

## Unreleased

- Rebuilt the primary SPA as modular React/TypeScript with Tailwind CSS, with event search, device center, candidates/exports and settings as the four main views.
- Added bounded ONVIF/private-subnet NVR discovery, read-only event/rule/notification audits and SADP/HiTools migration guidance.
- Added target-area search presets, normalized NVR event filters, search-scoped results, atomic one-frame previews and event/search provenance on exported clips.
- Accepted ADR-0004 and aligned the monorepo/package metadata on the MIT License.
- Pinned the monthly-retained BtbN FFmpeg 8.1 LGPLv3 Windows build, binary/source/license hashes and reproducible fetch verification.
- Replaced the GPL-only `libx264` transcode fallback with the verified `libopenh264` encoder from the pinned build.
- Isolated Windows pytest temporary data under a unique repository-local directory so stale or cross-identity `%TEMP%` ACLs cannot break verification.
- Fixed NVR onboarding so the display-only `name` field is excluded from the strict read-only probe request.
- Preserved successful NVR identity authentication when secondary time or channel endpoints deny access, reporting those capabilities as degraded instead of `AUTH_INVALID`.
- Added evidence-based NVR digital-channel discovery through the read-only InputProxy status endpoint when the local video-input endpoint is unavailable.
- Corrected Hikvision recording-search requests to use the protocol-defined `trackIDList` element.
- Changed Hikvision recording-search IDs to stable UUIDv5 values for firmware that rejects unhyphenated hexadecimal IDs.
- Fixed the default recording-search window to display local wall-clock time instead of UTC in `datetime-local` fields.
- Added a confirmed device-page action for deleting an NVR and its local credentials, indexes and derived clips without modifying NVR recordings.
- Established the monorepo product, architecture, contract, AI collaboration and CI/CD documentation baseline.
- Implemented the Engine timeline core and strict `timeline.v1` validation.
- Implemented a bounded, fixture-tested Hikvision ISAPI/RTSP adapter.
- Implemented the Desktop FastAPI/SQLite service, React/Vite UI, persistent jobs, timeline mapping and FFmpeg clip pipeline.
- Implemented the always-on Gateway core with clock health, bounded trajectory processing and durable export.
- Added exact dependency locks, module CI/security automation and explicitly gated Windows packaging/signing/SBOM/smoke workflows.
