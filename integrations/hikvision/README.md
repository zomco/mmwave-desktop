# Hikvision integration

[中文](README_CN.md)

This directory is the adapter boundary for Hikvision ISAPI and RTSP behavior. It is part of Desktop delivery but kept separate so a future ONVIF/other-brand adapter does not contaminate domain models.

## Adapter surface

```text
probe(connection) -> CapabilityReport
list_channels(connection) -> MediaChannel[]
search_recordings(query) -> Page<RecordingSpan>
search_historical_events(query) -> HistoricalEventResult
resolve_media(request) -> MediaResolution
```

The implementation supports fixture-based parsers, bounded pagination, Digest authentication, redacted diagnostics and model/firmware evidence. Historical event search uses the model-specific, read-only alarm-log endpoint and remains separately evidenced from recording-span search.

Never expose raw playback locators to the browser or persist credential-bearing URLs. Official native SDK support, if required for specific models, belongs in an isolated bridge process rather than the main Web process.

## Implemented baseline

`tracecue-hikvision` 0.1.0 provides a standard-library Digest transport with explicit TLS verification policy, bounded response reads, DTD/entity rejection, XML depth limits, device/time/channel parsing, evidence snapshots, bounded recording and historical-alarm-log pagination, start/stop event pairing, non-progress detection, ordinary/Smart rule inspection, endpoint-normalized grid/line/polygon overlays, bounded RTSP locator handling and recording-gap resolution. Checked-in fixtures are synthetic and explicitly are not hardware support evidence.

```powershell
python -m pip install -e "./integrations/hikvision[dev]"
python -m pytest integrations/hikvision/tests
```
