# Project material migration record

[中文](migration-record_CN.md)

- Migration date: 2026-08-12
- Destination: `D:\Users\zomco\Documents\GitHub\tracecue`
- Source context: product/architecture decisions developed alongside `mmwave-workspace` and its three Lab submodules.

## What moved

- TraceCue/Clipmark product problem, target customer, value and non-goals.
- Desktop/Gateway/Engine product and deployment boundaries.
- NVR-authoritative media architecture and FFmpeg strategy.
- Hikvision capability risk and compatibility-evidence model.
- HTTP API, SQLite/domain model and `timeline.v1` draft.
- Windows packaging, CI/CD, security, validation and UX guidance.
- AI collaboration rules, handoff format and developer contribution guidance.
- Commercial/open-source/channel assumptions and naming status.

## What did not move

No TraceCue source code previously existed in `mmwave-workspace`. No `mmwave-*` source, Git history, runtime submodule or Home Assistant dependency was copied. Those repositories remain the Lab and may produce fixtures/exports through explicit contracts.

## Source-of-truth change

From this migration onward, TraceCue product decisions belong in this repository's docs/ADRs. `mmwave-workspace` remains authoritative only for cross-repository Lab testing and research. Chat history is not a durable source of truth.

## Follow-up

Resolve ADR-0004 licensing before accepting external code, then begin M1. If new historical notes conflict with accepted ADRs, create a superseding ADR rather than silently merging assumptions.

## Implementation migration 0.1.0

Executable code now initializes Desktop SQLite schema version 1 on first start. New databases create the documented NVR, capability, channel, source, space/binding, interval, recording-span, job, clip and import tables. There was no prior executable database to migrate. A restart changes unfinished `running` jobs to `interrupted`; it never guesses that media work completed.

Gateway owns a separate internal SQLite store for its always-on intervals and bounded diagnostics. Desktop never reads that database; data crosses via `timeline.v1`.
