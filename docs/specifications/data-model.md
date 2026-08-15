# Data model draft

[中文](data-model_CN.md)

SQLite is the initial desktop store. Tables use stable opaque text IDs and UTC epoch milliseconds. Secrets are referenced, not stored.

| Table | Key fields | Purpose |
| --- | --- | --- |
| `nvrs` | `id`, host/ports, model, firmware, timezone, clock skew, `secret_ref` | Device identity and credential reference |
| `nvr_capabilities` | `nvr_id`, capability, status, evidence, observed time | Evidence-backed compatibility snapshot |
| `nvr_channels` | `id`, `nvr_id`, external ID, track IDs, device name, alias, online | Stable media-channel identity |
| `sources` | `id`, kind, external source ID, version | NVR, imported file, gateway or other producer |
| `source_channels` | `id`, `source_id`, external key, label, kind | Producer-local channel identity |
| `spaces` | `id`, name | Business location such as room or hallway |
| `space_media_channels` | `space_id`, NVR channel, role, priority, validity | One space to one/many camera views |
| `source_channel_bindings` | source channel, space, validity, correction policy | Sensor/source channel to business space |
| `intervals` | source/event identity, channel, type, raw and resolved times, quality, media window | Durable bookmark index |
| `recording_spans` | NVR channel, time range, class, locator, observed/expiry | Refreshable NVR coverage cache |
| `jobs` | kind, state, progress, error, payload, attempts, timestamps | Search/import/media work |
| `clips` | channel/window, actual coverage, path, codec, status, size | Derived media artifact index |
| `imports` | document/source IDs, content hash, status, diagnostics | Inspect/commit audit |
| `search_presets` | NVR, area, channel IDs, event types, last-used time | Reusable user-authored event filter |
| `search_results` | search job, interval | Exact provenance from a search session to its events |
| `nvr_event_audits` | NVR, safe summary JSON, observed time | Read-only event rule/notification snapshot |
| `event_previews` | interval, job, status, relative path | Derived JPEG preview index |
| `event_visual_analyses` | interval, job, status, verdict, bounded result JSON | Optional local detector/tracker/rule-geometry evidence for one NVR event |

## Constraints

- Unique `(nvr_id, external_channel_id)`.
- Unique `(source_id, external_channel_key)`.
- Unique `(source_id, source_event_id)` for intervals.
- `end_ms > start_ms`; media window covers the resolved interval.
- Scores/confidence are nullable or within their declared range.
- A clip path resolves under the configured clip root after normalization.
- Bindings and camera mappings may have validity ranges to survive replacement.

## Raw versus resolved time

Intervals preserve source time and store applied correction separately:

```text
raw_start_ms/raw_end_ms
clock_correction_ms
resolved_start_ms/resolved_end_ms
```

This makes later clock-policy changes auditable. Never overwrite raw imported timestamps.

## Recording locator

`recording_spans.locator` is adapter-private JSON and can expire. Browser APIs never receive credentials or raw locator content. Clip generation refreshes recording coverage instead of trusting a stale URI cached in a bookmark.

## Retention

- Intervals and mappings are durable metadata.
- Recording spans are a refreshable cache.
- Clips are derived and quota-controlled.
- Preview JPEGs are derived, stored under the same verified root and removed with their NVR-derived records.
- Visual-analysis rows are derived evidence. They retain model identity and bounded summaries, never frames, credentials or playback locators, and cascade with the source interval.
- Raw trajectory points are bounded diagnostics, not indefinite default storage.
- Deleting a clip removes both its index and verified in-root file; deleting an interval does not delete NVR media.
