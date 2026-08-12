# Changelog

[中文](CHANGELOG_CN.md)

All notable changes will be documented here after the first implementation milestone. Releases follow Semantic Versioning once a public API or distributable application exists.

## Unreleased

- Established the monorepo product, architecture, contract, AI collaboration and CI/CD documentation baseline.
- Implemented the Engine timeline core and strict `timeline.v1` validation.
- Implemented a bounded, fixture-tested Hikvision ISAPI/RTSP adapter.
- Implemented the Desktop FastAPI/SQLite service, React/Vite UI, persistent jobs, timeline mapping and FFmpeg clip pipeline.
- Implemented the always-on Gateway core with clock health, bounded trajectory processing and durable export.
- Added exact dependency locks, module CI/security automation and explicitly gated Windows packaging/signing/SBOM/smoke workflows.
