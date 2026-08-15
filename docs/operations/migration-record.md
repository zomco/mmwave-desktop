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

ADR-0004 was accepted on 2026-08-12 and the monorepo now uses MIT. If new historical notes conflict with accepted ADRs, create a superseding ADR rather than silently merging assumptions.

## Implementation migration 0.1.0

Executable code now initializes Desktop SQLite schema version 1 on first start. New databases create the documented NVR, capability, channel, source, space/binding, interval, recording-span, job, clip and import tables. There was no prior executable database to migrate. A restart changes unfinished `running` jobs to `interrupted`; it never guesses that media work completed.

Gateway owns a separate internal SQLite store for its always-on intervals and bounded diagnostics. Desktop never reads that database; data crosses via `timeline.v1`.

### Desktop schema v2-v6

Schema v2 added search presets/results, read-only NVR event-audit evidence, event JPEG previews and clip origin. Schema v3 adds the observed NVR UTC offset, multi-NVR camera scope for saved filters, expiring channel snapshots and cached event WebP animations. Existing presets retain their original camera list, existing interval/clip UTC timestamps do not change, and existing NVR rows fall back to parsing their stored POSIX timezone until a fresh probe supplies the explicit offset. Because playback-token mapping changed, schema v4 invalidates older JPEG preview cache rows; they are regenerated on demand while NVR originals remain untouched.

Schema v5 adds local Trace sessions, bounded search iterations, iteration-to-job links and per-session event review state. It stores stable local IDs, normalized event tags and UTC milliseconds only; it does not persist NVR credentials, authorization headers or playback locators. Existing searches and derived media are unchanged. The settings row gains local `night_start_hour` and `night_end_hour` defaults used only to construct browser-visible overnight windows.

The 2026-08-13 event-search compatibility update does not change the SQLite schema. New searches use bounded historical alarm logs instead of treating continuous recording files as events. Request validation now accepts only `motion`, `video_tamper`, `line_crossing` and `region_intrusion`; old sessions/presets containing `continuous` or catch-all `smart` remain stored for audit history, but the browser drops those labels before reuse. Cached event-audit JSON is versioned as schema `2` and refreshed read-only once so Smart rule endpoints use external camera IDs instead of stream track IDs. Existing intervals, clips and NVR media are unchanged.

The 2026-08-14 single-camera/two-stage search update also keeps SQLite schema v5. New search and preset requests require exactly one camera and at least one canonical event type. New Trace sessions accept one distinct time window; old multi-iteration sessions remain readable but are no longer restored by the browser. Result summaries add density, duration and event-type facets without loading event media. New historical events pair start/stop alarm logs and store duration evidence inside `attributes_json`; existing one-second indexed rows are not rewritten and therefore appear as “duration unknown” until a new search observes them. Event-audit JSON advances to schema `4` and is refreshed read-only to correct evidenced LineDetection and FieldDetection coordinates. New clips rebind returned playback locators to the requested resolved segment and label public time as NVR-indexed; existing clips and NVR originals are untouched.

The later 2026-08-14 timeline/detail refinement still requires no database migration. New requests require exactly one event type. Result summaries replace hourly density/type facets with bounded individual event spans for client-side zoom/drag selection; duration buckets are recomputed for the selected overlap window. New candidate clips trim only pre/post padding at midpoints between adjacent non-overlapping events from the same search/camera. Existing clips are not rewritten. Device hardware/firmware details are read on demand and are not persisted; unsupported per-camera identity remains null.

Schema v6 changes untouched legacy clip-context defaults from 5-second pre-roll/10-second post-roll to zero so new event candidates match the indexed event interval exactly. Explicitly customized non-default settings and existing clips remain unchanged. Media status responses now expose job-phase progress without storing new columns. ADR-0006 adds an in-memory-only, 15-minute LAN share token for a ready clip; tokens, LAN URLs and QR images are never persisted.

The subsequent camera-loading/activity-filter refinement requires no database migration. Existing ready snapshot rows become ten-minute stale-while-revalidate entries after their next successful refresh; an expired verified file remains readable while one refresh job runs. Result activity clusters and exact-duration bounds are derived from existing UTC interval rows at query time and persist no target identity, coordinates or inferred object class.
