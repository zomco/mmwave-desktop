# Contributing

[中文](CONTRIBUTING_CN.md)

TraceCue is currently owner-led. The repository welcomes design discussion and reproducible hardware findings, but external code contributions are paused until the licensing decision in ADR-0004 is resolved.

## Before opening work

1. Read `AGENTS.md`, the product brief and relevant module documentation.
2. Search existing issues and ADRs.
3. For a new capability or contract change, open a proposal before a large implementation.
4. For Hikvision findings, include model, firmware, endpoint, redacted response evidence and whether the behavior was reproduced.

## Development flow

- Branch names: `feat/…`, `fix/…`, `docs/…`, `chore/…`.
- Keep pull requests small and scoped to one outcome.
- Add tests before or with behavior changes.
- Update English and Chinese documentation together.
- Use Conventional Commit-style subjects where practical, for example `feat(engine): validate timeline intervals`.
- Never commit real NVR credentials, private IP inventories, customer footage or unredacted device exports.

## Pull request checklist

- Product boundary remains intact or an ADR explains the change.
- Public schemas and examples are synchronized.
- Error behavior is explicit and testable.
- Relevant tests and `python scripts/ci/verify_repo.py` pass.
- Hardware-specific claims identify the tested model and firmware.
- Security and license implications are documented.

## Review standard

Reviewers prioritize correctness, recoverability, secret handling, compatibility evidence and maintenance cost over abstraction density. A green CI result does not prove hardware compatibility.
