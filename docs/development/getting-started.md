# Developer getting started

[中文](getting-started_CN.md)

## Current state

The repository is contract-first: executable product modules have not landed. Your first checkout should still pass repository validation.

## Prerequisites

- Git 2.40+.
- Python 3.12+ for repository checks and the recommended control plane.
- Node.js LTS only after `desktop/package.json` exists.
- Windows 11 or a supported Windows 10 environment for product smoke tests.
- Access to a dedicated test NVR for hardware work; never use production credentials in fixtures.

## First checkout

```powershell
git clone https://github.com/zomco/tracecue.git
Set-Location tracecue
python scripts/ci/verify_repo.py
```

Then read, in order:

1. Root README and `AGENTS.md`.
2. Product brief and architecture overview.
3. The README of the module you will change.
4. Relevant specification and ADRs.

## Choosing work

Start from the next incomplete roadmap exit criterion. Prefer a vertical result such as "probe one NVR and store a capability report" over building generic framework layers.

For hardware work, create redacted fixtures and a compatibility record in the same change. For contract work, update English/Chinese docs, JSON schema, examples and tests together.

## Local configuration

Runtime configuration will use an untracked `.env` or user data directory only for development convenience; production secrets belong in Windows-protected storage. Never add real addresses or credentials to `.env.example`.

## Before requesting review

- Rebase/merge current `main` without destroying unrelated work.
- Run repository and module tests.
- Inspect `git diff` for secrets and accidental binary media.
- Update the handoff record if architectural context changed.
- State which hardware/firmware was and was not tested.
