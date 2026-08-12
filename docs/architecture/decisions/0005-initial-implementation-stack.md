# ADR-0005: Initial implementation stack

[中文](0005-initial-implementation-stack_CN.md)

- Status: Proposed
- Date: 2026-08-12

## Context

The product is maintained by one owner with substantial AI assistance. The stack must support fast iteration, readable contracts, Windows packaging, deterministic tests and subprocess-based media handling without making video a Python responsibility.

## Proposed decision

- Desktop backend: Python 3.12 and FastAPI.
- Desktop frontend: React, TypeScript and Vite.
- Engine: dependency-light Python package, usable without FastAPI/HA.
- Gateway: Python initially, with hardware adapters isolated from engine.
- Persistence: SQLite with explicit migrations.
- Media: pinned FFmpeg/FFprobe executables invoked as subprocesses.
- Packaging: one-folder Windows application and per-user installer.

## Consequences

The stack is approachable and contract-friendly, but Python packaging and Windows signing require deliberate automation. Frontend/backend version compatibility must be part of the package, not coordinated as separate deployments. Gateway resource limits must be measured before choosing low-power hardware.

## Acceptance conditions

Accept this ADR when M1 establishes a working skeleton, locked dependencies, tests on Windows and Linux, and a written package/version strategy. If the spike exposes a material blocker, replace the proposal before expanding the codebase.

## Implementation evidence

The 0.1.0 baseline now uses the proposed stack, includes exact npm/Python development locks, module tests and a Windows one-folder/installer strategy. The ADR remains proposed until hosted Windows and Linux CI complete and the gated package is built/smoke-tested with approved FFmpeg and signing inputs.
