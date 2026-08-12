# ADR-0004: License the TraceCue monorepo under MIT

[中文](0004-licensing-before-contributions_CN.md)

- Status: Accepted
- Date: 2026-08-12

## Context

The repository was initialized under GPL-3.0. Earlier product planning suggested a closed desktop/gateway integration with a potentially open engine. GPL-3.0 permits commercial distribution but imposes source and downstream obligations that may conflict with that boundary. Accepting third-party contributions before choosing a model can make later relicensing difficult.

## Options to evaluate

1. Keep the complete monorepo GPL-3.0 and commercialize distribution/support/hardware.
2. Use a permissive/open engine and proprietary desktop/gateway in separately licensed directories or repositories.
3. Use owner-controlled dual licensing with an explicit contributor agreement.
4. Keep the repository private/proprietary and publish selected components later.

## Decision

The owner relicensed the complete TraceCue monorepo, including `desktop`, `gateway`, `engine` and integrations, under the MIT License. Package metadata must declare `MIT`. Unless a future accepted ADR introduces a different module boundary, external contributions are submitted under the same MIT terms; no contributor license agreement or dual-license grant is required by this decision.

Third-party components retain their own licenses. In particular, bundling FFmpeg does not change TraceCue's MIT license and does not remove FFmpeg's LGPL obligations. Each binary release must preserve exact third-party notices, license texts, provenance and corresponding-source access.

## Consequences

- The repository root `LICENSE` is the source of truth for TraceCue code.
- Package manifests, contribution guidance and release metadata must stay aligned with MIT.
- External contributions are no longer blocked by this ADR, but still require normal review, authorship rights and license/security checks.
- A proprietary or dual-licensed module would require an explicit superseding ADR and a clean ownership record.
- FFmpeg and other third-party distribution obligations remain independent release gates.
