# Event-to-trace strategy

[中文](event-to-trace-strategy_CN.md)

## Product decision

For the NVR-first release, a **target area** is the set of camera views the user selects visually, grouped by recorder and stored as stable TraceCue camera IDs. A free-text area label is not a search predicate and is no longer shown. A saved filter contains the camera set and optional normalized event types and can be loaded for a later time window. Search results retain the NVR's raw classification privately while presenting a localized behavior name, event time, camera and search-session identity. The first page automatically loads cached JPEG previews; hovering lazily loads a cached three-second WebP preview. Users promote useful results to candidate clips, then download the confirmed MP4.

This is the recommended practical scheme for current Hikvision NVRs. It is useful without pretending that coarse recording metadata contains a precise physical trajectory.

## Options evaluated

| Option | Maturity | Value | Limitation | Decision |
| --- | --- | --- | --- | --- |
| Visual camera set + NVR event tags + saved filter | Uses stable local data and existing recording search | Users identify places from camera images; works across firmware with coarse classifications | A camera view is broader than a rule polygon; results can include false positives | Implement now |
| Read NVR event rules, schedules and trigger links | Vendor/ONVIF operations exist | Explains which event sources are enabled and how channels are configured | Endpoint/permissions vary; configuration does not prove historical occurrence | Implement read-only audit now; expand evidence per firmware |
| ONVIF event pull/subscription | Standard `GetEventProperties`/`PullMessages`; profiles define event conformance | Vendor-neutral live event topics and source data | Usually realtime, not a historical archive; desktop downtime loses events | Later, only with an always-on producer |
| Vendor fine historical-event search | Available on selected firmware/features | Finer rule/event identity and possibly region linkage | Not universal; must be tested and bounded per model/firmware | Experimental compatibility adapter after recording path is stable |
| Computer vision/embeddings over all recordings | Mature components exist separately | Can search visual semantics beyond NVR rules | High compute/storage/privacy burden; creates another analysis pipeline and new false positives | Not in the NVR-first release |
| Gateway/radar fusion | TraceCue architecture already supports durable external intervals | Can provide independent movement/trajectory evidence | Requires an always-on producer and certified physical hardware | Later milestone; not primary navigation |

ONVIF publishes the relevant standard operations in its [operation index](https://www.onvif.org/onvif/ver20/util/operationIndex.html). Hikvision publishes model-specific ISAPI capability and event material, including smart-rule capability data in its [open hardware documentation](https://open.hikvision.com/hardware/XMLs/DEVICE_ABILITY_SmartCalibrationCap.html). Neither source justifies assuming one universal historical-event endpoint.

## Implemented event-to-trace loop

1. Device center discovers candidates and verifies one with user credentials.
2. Channel aliases give stable cameras business meaning such as “north entrance.”
3. The read-only audit records known event enable, trigger-link state and bounded grid/polygon/line overlays when the device returns them.
4. Event search submits a bounded time, a visual camera set spanning one or more NVRs, and optional normalized event types.
5. TraceCue preserves raw NVR classification in evidence while mapping it to localized `motion`, `line_crossing`, `region_intrusion`, `smart` or `continuous` presentation.
6. Paged results automatically generate cached atomic JPEG previews; hover generates a bounded three-second animated WebP; confirmed results generate candidate MP4 files.
7. The MP4 record retains safe search/event provenance so export history remains understandable.

## Evidence boundary

- An enabled notification/rule means the device is configured to produce that event; it does not prove a historical event happened.
- A recording classification means the NVR described that span that way; it is not independent high-confidence validation.
- Realtime events missed while TraceCue is closed cannot be reconstructed unless the NVR offers a tested historical endpoint or an always-on Gateway stored them.
- Grid, polygon and line overlays remain camera/rule configuration. They explain a selected rule but do not prove that a historical recording span was triggered by that exact rule.

## Next evidence milestones

1. Record redacted audit/search/playback evidence for each supported model/firmware.
2. Add an evidence-backed adapter for fine historical event search where the hardware supports it.
3. Correlate event rule IDs and image regions with search records only when the device returns stable identifiers.
4. Measure event-to-clip time and missed-important-event recall with a cleared labelled dataset before claiming improvement over native clients.
