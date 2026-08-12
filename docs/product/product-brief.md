# Product brief

[中文](product-brief_CN.md)

## Problem

Apartment and small-property operators repeatedly scrub CCTV recordings to find a relevant visit or passage. Existing Hikvision NVRs already provide event/smart playback, but dense false positives from lights, reflections and activity outside the intended area often fill the timeline. The problem is poor signal-to-noise, not the absence of an event list.

## Product statement

TraceCue is a local Web application that runs on the user's Windows computer. The user adds an NVR, filters event intervals, and plays or exports a short clip. Later, high-confidence intervals from mmWave radar or other sensors become the primary bookmarks and drive time/channel seeks against the NVR.

```text
Authoritative NVR recording
        +
high-confidence time intervals
        ↓
reviewable bookmarks
        ↓
seek/export a short NVR clip
```

## Intended customer

- Apartment operators, sublessors and small property teams.
- Already know how to open the Hikvision client and review recordings.
- Do not want Docker, Home Assistant, firmware compilation or a second VMS.
- The payer is the operator/owner; later delivery can flow through local CCTV installers.

## Phases

| Phase | Capability | Honest value claim |
| --- | --- | --- |
| NVR foundation | Read supported Hikvision recording/event metadata, channel aliases, filters, playback/export | Faster organization and export; no false-positive superiority promise |
| Timeline | Import/consume `timeline.v1`, map source channels to spaces/NVR channels | Fewer high-confidence bookmarks, subject to measured recall |
| Productized sensing | Always-on gateway/radar companion without HA | End-to-end high-confidence timeline product |
| Expansion | Additional sources, optional LAN, channel distribution, ONVIF brands | Broader deployment and recurring support |

## Success criteria

1. A new Windows user follows documentation and reaches an event timeline from a supported Hikvision NVR within one hour.
2. For supported H.264 test cases, a selected event begins playback or yields a playable MP4 within a P95 target of 30 seconds.
3. No Docker, Home Assistant or cloud page directly accessing a private NVR is required.
4. TraceCue builds and runs without the `mmwave-*` repositories.
5. In a labelled golden dataset, high-confidence bookmarks reduce review volume while preserving an agreed important-event recall threshold.

## Non-goals

- Replacing the NVR as the recording system.
- Continuously transcoding every channel.
- Claiming that the same Hikvision event data magically removes Hikvision false positives.
- Making a WeChat Mini Program the primary client.
- Requiring a national on-site installation operation by the founder.
- Shipping Home Assistant as a customer prerequisite.

## Commercial shape

TraceCue is one product family. `desktop` is the main application, `gateway` is the optional/required companion for historical sensor timelines, and `engine` is the internal/openable technical core. A practical future packaging model is Basic (NVR workflow) and Pro/Radar (desktop plus always-on timeline producer).
