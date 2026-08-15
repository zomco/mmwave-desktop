# HTTP API v1 draft

[中文](http-api-v1_CN.md)

All routes are same-origin under `/api/v1`. JSON timestamps are RFC 3339 with explicit offsets. Errors use stable machine codes and a human-safe message; upstream bodies and credentials are never returned to the browser.

## Status and settings

```text
GET    /api/v1/status
GET    /api/v1/settings
PATCH  /api/v1/settings
GET    /api/v1/diagnostics
GET    /api/v1/diagnostics/export
```

`status` reports application version, schema version, FFmpeg availability and migration/recovery state. It must not expose filesystem secrets.

Settings include `night_start_hour` and `night_end_hour` integers in the inclusive range `0..23`. They describe local wall-clock boundaries used by the UI's overnight shortcuts; stored search bounds remain UTC milliseconds and API timestamps remain RFC 3339 with explicit offsets.

`diagnostics` previews a support bundle; `diagnostics/export` downloads the same JSON. Both redact NVR addresses, credentials, secret references, authorization headers, RTSP locators, filesystem paths and raw upstream bodies. The UI tells the user to review the bundle before sharing.

## NVRs and channels

```text
POST   /api/v1/nvrs/probe
POST   /api/v1/nvrs/discover
POST   /api/v1/nvrs
GET    /api/v1/nvrs
GET    /api/v1/nvrs/{nvr_id}
GET    /api/v1/nvrs/{nvr_id}/details
PATCH  /api/v1/nvrs/{nvr_id}
DELETE /api/v1/nvrs/{nvr_id}
POST   /api/v1/nvrs/{nvr_id}/sync-channels
GET    /api/v1/nvrs/{nvr_id}/channels
GET    /api/v1/nvrs/{nvr_id}/capabilities
GET    /api/v1/nvrs/{nvr_id}/event-audit
POST   /api/v1/nvrs/{nvr_id}/event-audit
PATCH  /api/v1/channels/{channel_id}
GET    /api/v1/channels/{channel_id}/snapshot
POST   /api/v1/channels/{channel_id}/snapshot
GET    /api/v1/channels/{channel_id}/snapshot/content
```

`nvrs/discover` accepts a bounded `timeout_seconds` from 0.5 to 5.0. It uses ONVIF WS-Discovery first and an unauthenticated port-80 probe on at most three directly attached private `/24` networks as fallback. A fallback result is only an ISAPI candidate and must pass `nvrs/probe` with user-supplied credentials before addition. `nvrs/{nvr_id}/details` performs an on-demand, read-only identity fetch. It returns NVR software/hardware fields and available per-camera connection/identity fields, explicitly leaves unsupported camera model/firmware fields null, and never returns credentials or raw XML. Event audit schema `4` reads ordinary motion/tamper and Smart line-crossing/intrusion settings per external camera ID; it returns bounded grid/polygon/line overlays where observed, never raw XML or credentials, and never modifies the NVR. Schema 4 normalizes evidenced LineDetection and FieldDetection bottom-origin vertical coordinates to the browser's top-left image coordinates. An older cached audit is refreshed read-only on first access. Channel snapshots are asynchronous, try an evidenced low-rate track first, and fall back to a bounded recent-recording search when live-view permission is denied. A verified image is fresh for ten minutes. When it expires, POST returns that cached image immediately while one background refresh runs; `stale` and `refreshing` make those states explicit. The two bounded job workers process at most two jobs concurrently and prioritize search/export work over queued camera refreshes. The fallback remains a camera-identification image, not a claim of realtime video.

Snapshot status also returns `source=live_low_rate|recent_recording|null`; it records the completed refresh path without exposing its RTSP locator or credentials.

Probe is read-only and returns structured evidence:

```json
{
  "reachable": true,
  "authenticated": true,
  "device": { "model": "redacted-example", "firmware": "v0" },
  "clock": {
    "observed_at": "2026-08-12T08:00:00Z",
    "estimated_skew_ms": -47000,
    "timezone": "+08:00"
  },
  "capabilities": {
    "record_search": "supported",
    "record_classification": "supported",
    "historical_event_search": "unknown",
    "realtime_event_stream": "unsupported",
    "playback_by_uri": "supported"
  },
  "warnings": [
    { "code": "CLOCK_SKEW", "message": "Device clock differs from this computer." }
  ]
}
```

Capability states are `supported`, `unsupported`, `unknown` and `degraded`. The server stores endpoint/status evidence separately from the public response.

Deleting an NVR removes its protected credential reference, capabilities, channels, NVR-originated indexed sources and local derived clips. It never modifies recordings stored on the NVR.

## Search and bookmarks

```text
POST /api/v1/search-jobs
GET  /api/v1/search-jobs/{job_id}
GET  /api/v1/search-jobs/{job_id}/results
GET  /api/v1/search-presets
POST /api/v1/search-presets
DELETE /api/v1/search-presets/{preset_id}
GET  /api/v1/trace-sessions
POST /api/v1/trace-sessions
GET  /api/v1/trace-sessions/{session_id}
DELETE /api/v1/trace-sessions/{session_id}
POST /api/v1/trace-sessions/{session_id}/iterations
GET  /api/v1/trace-sessions/{session_id}/results
PATCH /api/v1/trace-sessions/{session_id}/events/{bookmark_id}
GET  /api/v1/bookmarks
GET  /api/v1/bookmarks/{bookmark_id}
GET  /api/v1/bookmarks/{bookmark_id}/preview
POST /api/v1/bookmarks/{bookmark_id}/preview
GET  /api/v1/bookmarks/{bookmark_id}/preview/content
GET  /api/v1/bookmarks/{bookmark_id}/animation
POST /api/v1/bookmarks/{bookmark_id}/animation
GET  /api/v1/bookmarks/{bookmark_id}/animation/content
GET  /api/v1/bookmarks/{bookmark_id}/visual-analysis
POST /api/v1/bookmarks/{bookmark_id}/visual-analysis
```

Example search:

```json
{
  "nvr_id": "nvr_01",
  "channel_ids": ["channel_01"],
  "from": "2026-08-12T00:00:00+08:00",
  "to": "2026-08-13T00:00:00+08:00",
  "source_modes": ["historical_event_log"],
  "event_types": ["line_crossing"],
  "preset_id": "preset_01"
}
```

The effective target area is exactly one stable camera ID; the browser groups camera images by NVR and renders them as a radio choice, so there is no recorder or free-text area filter. `channel_ids` therefore contains exactly one item. `event_types` also contains exactly one of `motion`, `video_tamper`, `line_crossing` or `region_intrusion`. Continuous recording, catch-all Smart labels and multi-type requests are rejected. Presets persist one camera ID plus one event tag. Each job reads bounded historical alarm logs and pairs matching start/stop entries for the same camera and type, up to one hour. A paired event stores its real `event_duration_ms`; an unpaired event stores `null` with `duration_source: "unknown"`. `result.truncated` reports an adapter limit. Recording search is deferred until preview/clip generation. `search-jobs/{job_id}/results?limit=12&offset=0` returns a bounded page, total count and `has_more`, and only includes events produced by that search. JPEG preview creation is asynchronous and cached per event. Preview and animation status responses include normalized job `progress` from `0` to `1`; it is phase progress rather than an upstream byte counter. The animation route lazily creates a verified, bounded three-second animated WebP for hover playback. All files are written atomically under the derived-media root.

Visual analysis is optional and currently accepts only `line_crossing` and `region_intrusion` bookmarks. POST is idempotent while an analysis is queued, running or ready. It resolves at most a 30-second context window, asks FFmpeg for fixed-size BGR frames, runs the configured local ONNX detector, tracks supported person/vehicle targets and compares their ground trajectories with the cached evidence-backed rule line/polygon. The cached response reports `confirmed_trigger`, `target_present_no_trigger`, `no_supported_target_detected` or `uncertain`, plus model identity, analyzed window, optional visual trigger time and phase progress. Negative evidence never mutates or deletes the NVR bookmark. A confirmed trigger may atomically replace the hover WebP with a short proof window centered on the reconstructed trigger.

A Trace session persists one camera/event-type scope and accepts one bounded time iteration. Create a session with `{"channel_ids":["channel_01"],"event_types":["motion"]}`, then append a window with `{"from":"2026-08-12T18:00:00+08:00","to":"2026-08-13T06:00:00+08:00","label":"Time range"}`. Repeating that exact window is idempotent; a different second window returns `TRACE_SESSION_WINDOW_FIXED`, and the client must create a new search. The persisted job kind remains `recording_search` for schema compatibility, but its event source is the historical alarm log.

`trace-sessions/{session_id}/results` accepts bounded `limit`/`offset`, `review_state=active|all|unreviewed|reviewed|excluded|candidate`, optional paired RFC 3339 `from`/`to`, `duration_class=unknown|under_5s|5_to_30s|over_30s`, exact inclusive `min_duration_ms`/`max_duration_ms`, `activity_mode=all|isolated|clustered`, and `summary_only`. Events whose gap from the running end of the preceding event is at most 30 seconds form one stable activity cluster; a one-event cluster is `isolated`, while larger clusters are `clustered`. The response always contains global review counts, up to 2000 individual `timeline` spans (`id`, `start_at`, `end_at`, nullable `duration_ms`, `cluster_size`), `timeline_truncated`, the active `selected_window`, `duration_buckets`, `duration_range`, `activity_counts`, and `activity_cluster_gap_ms`. Time filters use interval-overlap semantics. Duration/activity facets are recomputed for the selected time window; duration statistics also follow the selected activity mode before duration bounds are applied. With `summary_only=true`, `items` is empty and no preview work is triggered. A normal response returns the filtered page and search-job identity required for a candidate clip. `active` excludes only explicitly excluded events. Review patches persist `unreviewed`, `reviewed`, `excluded` or `candidate` per session. Session records contain stable IDs and event tags, never credentials, authorization headers or playback locators.

Large searches are jobs. Bookmark lists use opaque server cursors; Hikvision pagination tokens/positions do not leak through the API.

## Clips and jobs

```text
POST   /api/v1/clips
GET    /api/v1/clips
GET    /api/v1/clips/{clip_id}
GET    /api/v1/clips/{clip_id}/content
POST   /api/v1/clips/{clip_id}/share
DELETE /api/v1/clips/{clip_id}
GET    /api/v1/jobs
GET    /api/v1/jobs/{job_id}
POST   /api/v1/jobs/{job_id}/cancel
```

Create by bookmark or explicit channel/window, never by a browser-supplied RTSP URL:

```json
{
  "bookmark_id": "interval_01",
  "search_job_id": "job_search_01",
  "window_override": { "pre_roll_ms": 0, "post_roll_ms": 0 },
  "audio_policy": "prefer"
}
```

When created from a bookmark, the default and Event Search UI export exactly the indexed event start/end interval (`pre_roll_ms=0`, `post_roll_ms=0`) with no implicit duration cap. Non-zero contextual padding remains an explicit API/settings option. The public clip record includes safe `origin` fields: bookmark ID, search job ID, area label, channel label, event type/classification, event window, `time_basis: "nvr_index"`, whether explicitly requested adjacent-event padding was trimmed, and whether an explicit candidate-duration cap was applied. For adjacent non-overlapping events from the same camera/search, only non-zero contextual padding is clipped at a whole-second midpoint that remains between event bodies; event bodies are never trimmed. Genuine event-body overlaps remain overlaps. The response never includes an RTSP locator or credential. Explicit channel/window clips have `origin: null`. Clip records include phase `progress`; the browser additionally calculates byte progress while downloading the ready MP4.

`clips/{clip_id}/share` is an explicit local-user action governed by ADR-0006. It starts or reuses a separate private-interface listener and returns a locally generated capability URL plus its expiry. A 256-bit in-memory token authorizes only `GET`/`HEAD` access to a minimal page and bounded Range delivery for that one ready clip for 15 minutes. It does not expose the loopback API, NVR address, credentials or filesystem path. The QR is generated locally; the URL is not sent to a third-party QR service.

Internal event and clip time remains UTC. Before FFmpeg, each locator's broad recording bounds are replaced with the resolved requested media-segment bounds. For tested Hikvision firmware whose compact RTSP playback tokens are interpreted as device-local wall time despite their `Z` suffix, the media boundary then translates only those locator tokens using the observed device offset. Public event/clip timestamps are not shifted. An embedded camera OSD watermark uses the camera's own clock and may differ from NVR-indexed event time; TraceCue reports this mismatch instead of guessing a correction.

`audio_policy` is `prefer`, `preserve` or `omit`. `prefer` transcodes supported
audio to AAC and falls back to a silent clip when an NVR advertises an
undecodable private audio payload. `preserve` is strict and fails instead of
silently dropping audio. Source video is inspected before rendering: H.264 is
remuxed where possible and other codecs are converted to H.264 for browser
playback.

Job states are `queued`, `running`, `succeeded`, `failed`, `cancelled` and `interrupted`. On restart, prior `running` jobs become `interrupted`; recovery is an explicit new attempt. Clip content supports bounded HTTP Range requests.

## Timeline imports and mappings

```text
POST /api/v1/timeline-imports/inspect
GET  /api/v1/timeline-imports/{import_id}
POST /api/v1/timeline-imports/{import_id}/commit
GET  /api/v1/sources
GET  /api/v1/source-channels
PUT  /api/v1/source-channels/{source_channel_id}/binding
```

Inspect validates schema, IDs, timestamps and mappings without mutating interval tables. Commit is idempotent and references the inspected content hash. Unmapped channels can be stored but cannot request clips.

## Error envelope

```json
{
  "error": {
    "code": "RECORDING_GAP",
    "message": "The NVR does not cover the complete requested time window.",
    "request_id": "req_01",
    "details": { "coverage": "partial" }
  }
}
```

Initial stable error families: `AUTH_*`, `NVR_*`, `CAPABILITY_*`, `CLOCK_*`, `TIMELINE_*`, `MAPPING_*`, `RECORDING_*`, `MEDIA_*`, `STORAGE_*` and `JOB_*`.
