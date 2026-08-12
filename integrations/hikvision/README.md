# Hikvision integration

[中文](README_CN.md)

This directory is the adapter boundary for Hikvision ISAPI and RTSP behavior. It is part of Desktop delivery but kept separate so a future ONVIF/other-brand adapter does not contaminate domain models.

## Adapter surface

```text
probe(connection) -> CapabilityReport
list_channels(connection) -> MediaChannel[]
search_recordings(query) -> Page<RecordingSpan>
search_intervals(query) -> Page<SourceInterval>
resolve_media(request) -> MediaResolution
```

The implementation must support fixture-based parsers, bounded pagination, Digest authentication, redacted diagnostics and model/firmware evidence. `search_intervals` may be unsupported while `search_recordings` works.

Never expose raw playback locators to the browser or persist credential-bearing URLs. Official native SDK support, if required for specific models, belongs in an isolated bridge process rather than the main Web process.
