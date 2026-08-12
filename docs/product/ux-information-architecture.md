# UX information architecture

[中文](ux-information-architecture_CN.md)

## First run

```text
Start TraceCue
└─ Add NVR
   ├─ Address and credentials
   ├─ Connection and clock test
   ├─ Capability report
   ├─ Channel synchronization
   └─ Room/channel aliases
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

A persistent notice must say that candidates come from NVR recording/event metadata and can contain false positives. Do not label this view "high confidence" or "noise reduced."

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
