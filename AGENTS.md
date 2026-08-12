# Instructions for AI collaborators

[中文](AGENTS_CN.md)

Read this file completely before changing the repository. Then read the documentation routed by the task. AI-generated changes follow the same review, test, security and licensing requirements as human changes.

## Mission

TraceCue helps non-enthusiast apartment and small-property operators find relevant NVR recordings faster. Preserve these invariants:

1. The NVR is the authoritative video store; TraceCue indexes metadata bookmarks.
2. The default desktop service binds to `127.0.0.1`.
3. Media work uses FFmpeg and browser video, not Python frame decoding/rendering.
4. NVR-only data must not be marketed as high-confidence false-positive reduction.
5. `desktop`, `gateway` and `engine` share this monorepo but keep explicit interfaces.
6. TraceCue must build and run without Home Assistant or any `mmwave-*` repository.
7. Historical sensor timelines require an always-on producer; an on-demand desktop app cannot reconstruct missed radar history.

## Before editing

1. Check `git status` and preserve unrelated user changes.
2. Read the nearest module `README.md` and its Chinese counterpart.
3. Read relevant specifications and accepted ADRs.
4. If a change alters a public contract, update both language versions, examples, schema and tests in the same change.
5. If a decision conflicts with an accepted boundary, write or update an ADR before implementation.

## Documentation routing

| Task | Read first |
| --- | --- |
| Product scope or UX | `docs/product/`, then `docs/architecture/boundaries.md` |
| Desktop/API/NVR/media | `desktop/README.md`, `docs/specifications/http-api-v1.md`, Hikvision and packaging docs |
| Gateway/radar collection | `gateway/README.md`, architecture overview, timeline spec |
| Engine/interval logic | `engine/README.md`, timeline spec, data model |
| CI/release/security | `docs/operations/`, `CONTRIBUTING.md`, `SECURITY.md` |
| Cross-repository mmWave research | `docs/architecture/boundaries.md`; never create a runtime import |

## Change rules

- Keep English and Chinese documents semantically aligned. English uses `.md`; Chinese uses `_CN.md`.
- Store internal time as UTC milliseconds. External timestamps must be RFC 3339 with an explicit offset.
- Do not persist passwords, authorization headers or credential-bearing RTSP URIs in SQLite or logs.
- Invoke FFmpeg with an argument array and no shell interpolation.
- Treat NVR responses as untrusted input. Bound XML/JSON sizes and disable XML external entities.
- Capability support is evidence-based and per model/firmware; never infer a universal Hikvision feature.
- Use stable internal IDs. Do not use a Hikvision channel/track number as a business primary key.
- Generated clips are derived artifacts. Write to `.partial`, verify, then rename atomically.
- New dependencies require a reason, license check and owner-maintenance assessment.
- Do not change `LICENSE` or accept contribution licensing terms without an explicit owner decision.

## Tests and completion

Run `python scripts/ci/verify_repo.py` for every documentation or structure change. Once module manifests exist, run the module commands documented in `docs/development/testing.md`. Report what was run and what remains unverified.

A task is complete only when implementation, tests, bilingual docs, contracts/examples and relevant migration notes agree. Never describe a planned capability as implemented.

## Handoff format

End substantial work with:

- Outcome and affected product slice.
- Files/contracts changed.
- Commands and results.
- Known risks or unverified hardware behavior.
- Next smallest executable step.

Use `docs/ai/handoff.md` for longer handoffs.
