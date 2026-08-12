# AI/human handoff record

[中文](handoff_CN.md)

This file stores durable context that would otherwise be lost between AI sessions. Append concise dated entries; move accepted decisions into ADRs/specifications instead of treating this as authority.

## Current handoff — 2026-08-12

### Outcome

The repository baseline defines TraceCue as one product family with Desktop, Gateway and Engine in a monorepo. Product code has not yet been implemented.

### Accepted boundaries

- Loopback local Web Desktop.
- NVR is authoritative media storage.
- NVR-only data has no high-confidence marketing claim.
- Historical sensor data requires an always-on producer.
- No runtime dependency on HA or `mmwave-*` repositories.

### Blocking decision

MIT applies to TraceCue code under accepted ADR-0004. Public binaries must still satisfy the pinned FFmpeg LGPL/source/notices posture and every other third-party obligation.

### Next smallest executable task

Implement M1's read-only Hikvision protocol probe against one owner-controlled model/firmware, with redacted fixtures and no media export yet.

### Unverified

- Exact historical event endpoints for target NVR models.
- Final language/framework choices.
- Windows signing eligibility and certificate provider.
- FFmpeg build/provenance selected for distribution.
