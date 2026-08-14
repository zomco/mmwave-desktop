# UX information architecture

[中文](ux-information-architecture_CN.md)

## Primary navigation (NVR-first release)

```text
Event search
├─ Required exact time, one visual camera and exactly one behavior type
├─ NVR-grouped camera snapshots refreshed once on page entry as a single-choice target-area selector
├─ Selected camera overlays the selected event type's evidenced rule boundary
├─ Saved filters
├─ Summary-only first pass with a single-track zoomable event-span timeline and duration facets
├─ Click an event span or drag a sub-window; duration facets recompute for that window
├─ Paged preview gallery only after a secondary timeline/all-events choice
├─ Hover motion and durable reviewed/excluded state
└─ Generate candidate clip

Device center
├─ Automatic LAN discovery
├─ Select device and enter credentials
├─ Camera cards combining snapshots, aliases and event notification state
├─ Read-only rule selection with grid/polygon/line overlays
└─ On-demand NVR/camera hardware and firmware details

Candidates and exports
├─ Browser playback, generation/download progress and MP4 download
├─ Compact event behavior plus camera/time title without duplicate provenance fields
└─ Explicit 15-minute, token-scoped LAN QR share for one ready clip

Settings
└─ Local overnight start/end hours
```

## NVR-only navigation

```text
Find recordings
├─ Date/time
├─ Room/channel
├─ NVR-originated type/filter
├─ Candidate list
└─ Clip detail: generate, play, export

Exported clips
Devices
Diagnostics and settings
```

A persistent notice says candidates come from NVR recording/event metadata and can contain false positives. Do not label this view "high confidence" or "noise reduced." Sources/mappings and comparison are not primary-navigation items until Gateway/Engine evidence is ready.

## Timeline-backed navigation

```text
Worth reviewing (default)
├─ High-confidence bookmarks
├─ Quality/source filters
└─ Clip detail

All candidates
├─ High-confidence timeline
└─ NVR-originated candidates

Comparison
├─ Review-volume change
├─ Unmatched/uncertain intervals
└─ Clock health

Sources and mappings
Exported clips
Devices
Diagnostics and settings
```

If the timeline is stale, a source is unmapped, a quality gate fails or clock skew exceeds policy, the UI must show degraded state. It must not silently fall back to NVR data while retaining a high-confidence label.
