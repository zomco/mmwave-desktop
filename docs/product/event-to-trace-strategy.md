# Event-to-trace strategy

[中文](event-to-trace-strategy_CN.md)

## Product decision

For the NVR-first release, a **target area** is one camera view selected visually from NVR-grouped images and stored as a stable TraceCue camera ID. One camera per query bounds NVR and preview work and matches how users identify a place. A free-text area label is not a search predicate. A saved filter contains that camera and one or more required normalized event types. Each Trace search has one bounded time window; changing the time creates a new search rather than accumulating a hidden multi-night session. The first pass returns statistics only: hourly event density, paired alarm duration buckets and event-type composition. Event cards and cached JPEG/WebP media are requested only after the user explicitly selects a secondary statistic or chooses all events. Review state remains durable, and confirmed results become candidate MP4 files. This release intentionally does not accept natural-language search input.

This is the recommended practical scheme for current Hikvision NVRs. It is useful without pretending that coarse recording metadata contains a precise physical trajectory.

## Options evaluated

| Option | Maturity | Value | Limitation | Decision |
| --- | --- | --- | --- | --- |
| Visual camera set + NVR alarm logs + saved filter | Uses stable local data and an evidenced historical endpoint | Users identify places from camera images; event times map back to continuous media | Alarm-log support/retention varies by firmware; results can include false positives | Implemented for evidenced Hikvision firmware |
| Read NVR event rules, schedules and trigger links | Vendor/ONVIF operations exist | Explains which event sources are enabled and how channels are configured | Endpoint/permissions vary; configuration does not prove historical occurrence | Implement read-only audit now; expand evidence per firmware |
| ONVIF event pull/subscription | Standard `GetEventProperties`/`PullMessages`; profiles define event conformance | Vendor-neutral live event topics and source data | Usually realtime, not a historical archive; desktop downtime loses events | Later, only with an always-on producer |
| Vendor fine historical-event search | Available on selected firmware/features | Finer event identity without treating long recording files as events | Not universal; must be tested and bounded per model/firmware | Implemented ISAPI alarm-log adapter; expand evidence per model |
| Computer vision/embeddings over all recordings | Mature components exist separately | Can search visual semantics beyond NVR rules | High compute/storage/privacy burden; creates another analysis pipeline and new false positives | Not in the NVR-first release |
| Gateway/radar fusion | TraceCue architecture already supports durable external intervals | Can provide independent movement/trajectory evidence | Requires an always-on producer and certified physical hardware | Later milestone; not primary navigation |

ONVIF publishes the relevant standard operations in its [operation index](https://www.onvif.org/onvif/ver20/util/operationIndex.html). Hikvision publishes model-specific ISAPI capability and event material, including smart-rule capability data in its [open hardware documentation](https://open.hikvision.com/hardware/XMLs/DEVICE_ABILITY_SmartCalibrationCap.html). Neither source justifies assuming one universal historical-event endpoint.

## Implemented event-to-trace loop

1. Device center discovers candidates and verifies one with user credentials.
2. Channel aliases give stable cameras business meaning such as “north entrance.”
3. The read-only audit separates ordinary `motion`/`video_tamper` from Smart `line_crossing`/`region_intrusion`, records enable/trigger-link state and draws bounded grid/polygon/line overlays when returned. Selecting a Smart type retains only cameras with supported capability evidence.
4. Event search submits a bounded time, exactly one visual camera and at least one normalized event type. It reads historical alarm logs; continuous recording files are excluded as event candidates.
5. TraceCue preserves the raw alarm-log `metaId` in safe evidence while mapping it to localized `motion`, `video_tamper`, `line_crossing` or `region_intrusion` presentation. Vague “other Smart event” and continuous-recording filters are not exposed.
6. Start/stop alarm-log entries are paired when possible. Unknown durations remain explicitly unknown; they are never represented as synthetic one-second events in the UI.
7. A summary-only response exposes hourly density, duration and event-type facets. Only after a secondary choice does a six-item page generate cached atomic JPEG previews; hover generates a bounded three-second animated WebP.
8. Confirmed results generate candidate MP4 files whose playback locators are rebound to the resolved requested media span. Public times remain NVR-indexed; camera OSD watermarks may differ when camera and NVR clocks are not synchronized.

## Evidence boundary

- An enabled notification/rule means the device is configured to produce that event; it does not prove a historical event happened.
- An alarm-log entry is an NVR-originated bookmark, not independent high-confidence validation. Continuous recording classification is only used to resolve media around that bookmark.
- Realtime events missed while TraceCue is closed cannot be reconstructed unless the NVR offers a tested historical endpoint or an always-on Gateway stored them.
- Grid, polygon and line overlays remain camera/rule configuration. They explain a selected rule but do not prove that a historical recording span was triggered by that exact rule.

## Next evidence milestones

1. Record redacted audit/search/playback evidence for each supported model/firmware.
2. Expand the evidence-backed historical alarm-log adapter to additional model/firmware combinations and event classes.
3. Correlate event rule IDs and image regions with search records only when the device returns stable identifiers.
4. Measure event-to-clip time and missed-important-event recall with a cleared labelled dataset before claiming improvement over native clients.
