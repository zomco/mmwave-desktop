# ADR-0004: Resolve licensing before external code contributions

[中文](0004-licensing-before-contributions_CN.md)

- Status: Proposed / blocking external code contributions
- Date: 2026-08-12

## Context

The repository was initialized under GPL-3.0. Earlier product planning suggested a closed desktop/gateway integration with a potentially open engine. GPL-3.0 permits commercial distribution but imposes source and downstream obligations that may conflict with that boundary. Accepting third-party contributions before choosing a model can make later relicensing difficult.

## Options to evaluate

1. Keep the complete monorepo GPL-3.0 and commercialize distribution/support/hardware.
2. Use a permissive/open engine and proprietary desktop/gateway in separately licensed directories or repositories.
3. Use owner-controlled dual licensing with an explicit contributor agreement.
4. Keep the repository private/proprietary and publish selected components later.

## Temporary decision

Preserve the existing `LICENSE`; do not imply a different license. Pause external code contributions and third-party code copying until the owner chooses a model with appropriate legal advice. Documentation and issue discussion may continue.

## Resolution requirements

Record chosen licenses per module, contribution terms, FFmpeg distribution posture, third-party notices and migration steps. Replace this ADR with an accepted superseding decision before the first external code contribution or public binary.
