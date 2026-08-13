# UX information architecture

[中文](ux-information-architecture_CN.md)

## Primary navigation (NVR-first release)

```text
Event search
├─ Required exact time, one visual camera and one or more behavior types
├─ NVR-grouped camera snapshots as a single-choice target-area selector
├─ Saved filters
├─ Summary-only first pass with hourly density, duration and event-type facets
├─ Paged preview gallery only after a secondary facet is chosen
├─ Hover motion and durable reviewed/excluded state
└─ Generate candidate clip

Device center
├─ Automatic LAN discovery
├─ Select device and enter credentials
├─ Camera cards combining snapshots, aliases and event notification state
└─ Read-only rule selection with grid/polygon/line overlays

Candidates and exports
├─ Browser playback and MP4 download
└─ NVR-indexed event/clip time, camera and search provenance

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
