# UX information architecture

[中文](ux-information-architecture_CN.md)

## Primary navigation (NVR-first release)

```text
Event search
├─ Time and business area
├─ Camera and event-type filters
├─ Saved filters
├─ Event preview gallery
└─ Generate candidate clip

Device center
├─ Automatic LAN discovery
├─ Select device and enter credentials
├─ Channels and business aliases
└─ Read-only event/rule/notification audit

Candidates and exports
├─ Browser playback and MP4 download
└─ Search, area, camera and event provenance

Settings
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
