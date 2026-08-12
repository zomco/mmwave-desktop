# CI/CD design

[中文](ci-cd_CN.md)

CI/CD is optimized for a single maintainer without making one machine the only source of truth.

## Pull request and push CI

`ci.yml` always runs the repository contract check. Module jobs activate automatically when their manifests exist. A stable final quality-gate job makes branch protection independent from optional skipped jobs.

Required future branch protection:

- Pull request required for `main` once collaborators join.
- `quality-gate` required.
- Conversation resolution required.
- No force pushes/deletion.
- CODEOWNERS review for contracts, security and workflows when another maintainer exists.

## Security automation

`security.yml` runs a lightweight secret/path audit on pushes and a weekly schedule. Pull requests also use dependency review. Add CodeQL languages when executable Python/TypeScript code lands; do not run a misleading empty scan.

Dependabot currently manages GitHub Actions. Add npm/pip ecosystems only after their manifests exist.

## Release workflow

`release.yml` is intentionally gated by a real Windows packaging script and release manifest. Until implementation lands, manual/tag release attempts fail rather than publishing documentation as a fake product binary.

A publishable release must:

1. Pass all CI and security checks.
2. Build on a clean hosted Windows runner.
3. Run unit/contract and installed smoke tests.
4. Generate SBOM/provenance, checksums and third-party notices.
5. Sign binaries and installer.
6. Upload immutable artifacts.
7. Publish only from a version tag matching the application version.
8. Keep a rollback/revocation record.

## Secrets

Use GitHub Environments for release approvals and signing secrets. OIDC-based short-lived credentials are preferred over long-lived keys. Fork pull requests never receive release or signing secrets.

## Reproducibility

Pin language/runtime and FFmpeg versions, lock dependencies, keep migration tests and store artifact hashes. A release is not complete if it can only be rebuilt on the maintainer's workstation.
