# Product brief

[中文](product-brief_CN.md)

## Problem

Apartment and small-property operators repeatedly scrub CCTV recordings to find a relevant visit or passage. Existing Hikvision NVRs already provide event/smart playback, but dense false positives from lights, reflections and activity outside the intended area often fill the timeline. The problem is poor signal-to-noise, not the absence of an event list.

## Product statement

TraceCue is a local review application. `mmwave-engine` tags a passage from 2-D radar tracks. That tag opens a still and a short clip from the live camera stream. NVR smart labels, such as region intrusion and line crossing, are a later low-weight hint. They have dense false positives and must be cleaned before they can rank a radar event or enter an offline reference set. Seeking the NVR timeline remains an optional cold archive ([ADR-0008](../architecture/decisions/0008-local-clip-review.md), [ADR-0009](../architecture/decisions/0009-radar-tag-outranks-nvr.md)).

```text
mmwave-engine tag (highest weight)
        +
optional cleaned NVR label
        ↓
still / short live clip
        ↓
NVR timeline only if the clip is missing
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
4. The NVR cold-archive path builds without `mmwave-*`. Radar review may depend on the published `mmwave-engine` package and must not import `mmwave-fusion` or `tracecue-engine` into that package.
5. In a labelled golden dataset, high-confidence bookmarks reduce review volume while preserving an agreed important-event recall threshold.

## Non-goals

- Replacing the NVR as the recording system.
- Continuously transcoding every channel.
- Claiming that the same Hikvision event data magically removes Hikvision false positives.
- Making a WeChat Mini Program the primary client.
- Requiring a national on-site installation operation by the founder.
- Shipping Home Assistant as a customer prerequisite.

## Commercial shape

TraceCue is one product family. `desktop` is the review application. `gateway` is the always-on producer. `mmwave-engine` is the shared radar tag. `tracecue-engine` in this repository is the cold-archive timeline and the offline reference export, not a runtime helper of `mmwave-engine` ([ADR-0009](../architecture/decisions/0009-radar-tag-outranks-nvr.md)).
