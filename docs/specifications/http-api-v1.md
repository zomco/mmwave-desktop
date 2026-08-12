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

`diagnostics` previews a support bundle; `diagnostics/export` downloads the same JSON. Both redact NVR addresses, credentials, secret references, authorization headers, RTSP locators, filesystem paths and raw upstream bodies. The UI tells the user to review the bundle before sharing.

## NVRs and channels

```text
POST   /api/v1/nvrs/probe
POST   /api/v1/nvrs/discover
POST   /api/v1/nvrs
GET    /api/v1/nvrs
GET    /api/v1/nvrs/{nvr_id}
PATCH  /api/v1/nvrs/{nvr_id}
DELETE /api/v1/nvrs/{nvr_id}
POST   /api/v1/nvrs/{nvr_id}/sync-channels
GET    /api/v1/nvrs/{nvr_id}/channels
GET    /api/v1/nvrs/{nvr_id}/capabilities
GET    /api/v1/nvrs/{nvr_id}/event-audit
POST   /api/v1/nvrs/{nvr_id}/event-audit
PATCH  /api/v1/channels/{channel_id}
```

`nvrs/discover` accepts a bounded `timeout_seconds` from 0.5 to 5.0. It uses ONVIF WS-Discovery first and an unauthenticated port-80 probe on at most three directly attached private `/24` networks as fallback. A fallback result is only an ISAPI candidate and must pass `nvrs/probe` with user-supplied credentials before addition. The event audit reads selected motion/smart rule and trigger-link settings; it returns safe summaries, never raw XML or credentials, and never modifies the NVR.

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
GET  /api/v1/bookmarks
GET  /api/v1/bookmarks/{bookmark_id}
GET  /api/v1/bookmarks/{bookmark_id}/preview
POST /api/v1/bookmarks/{bookmark_id}/preview
GET  /api/v1/bookmarks/{bookmark_id}/preview/content
```

Example search:

```json
{
  "nvr_id": "nvr_01",
  "channel_ids": ["channel_01"],
  "from": "2026-08-12T00:00:00+08:00",
  "to": "2026-08-13T00:00:00+08:00",
  "source_modes": ["record_classification"],
  "area_name": "north entrance",
  "event_types": ["motion", "line_crossing"],
  "preset_id": "preset_01"
}
```

`area_name` is a user-authored business label: the effective area mapping is the selected stable camera IDs plus event-type tags. It is not asserted to be an NVR image polygon. Presets persist that mapping. `search-jobs/{job_id}/results` returns only events produced by that search, which keeps later clips attributable to an exact session. Preview creation is an asynchronous FFmpeg job that writes one verified JPEG atomically under the derived-media root.

Large searches are jobs. Bookmark lists use opaque server cursors; Hikvision pagination tokens/positions do not leak through the API.

## Clips and jobs

```text
POST   /api/v1/clips
GET    /api/v1/clips
GET    /api/v1/clips/{clip_id}
GET    /api/v1/clips/{clip_id}/content
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
  "window_override": { "pre_roll_ms": 5000, "post_roll_ms": 10000, "max_duration_ms": 30000 },
  "audio_policy": "prefer"
}
```

When created from a bookmark, the public clip record includes safe `origin` fields: bookmark ID, search job ID, area label, channel label, event type/classification, event window and whether an explicitly requested candidate-duration cap was applied. It never includes an RTSP locator or credential. Explicit channel/window clips have `origin: null`.

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
