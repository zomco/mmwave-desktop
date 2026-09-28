# ADR-0009: Radar tags outrank NVR labels

[中文](0009-radar-tag-outranks-nvr_CN.md)

- Status: Accepted
- Date: 2026-09-28
- Related: [ADR-0008](0008-local-clip-review.md)

## Context

TraceCue and mmwave-fusion both use mmWave tracks to tag security video for later review. Some NVRs already emit their own labels, such as region intrusion and line crossing. Those labels have dense false positives from lights, shadows and weather. They are useful only after cleaning, and they are not radar observations.

`mmwave-engine` is the shared tracker. `tracecue-engine` is this repository's timeline library. Collaborators must not merge them, and must not treat raw NVR labels as training truth.

## Decision

1. `mmwave-engine` is the highest-weight video tag. Its `enter`, `dwell` and `traverse` events decide which still or short clip opens. NVR labels never enter `FusionEngine.step()`.
2. A later corroboration step may rank a radar event against a cleaned NVR label in the same zone and time window. Ranking does not rewrite the radar event. `radar_only` stays visible. `nvr_only` is a low-weight hint, not a confirmed person. A time match with a zone mismatch is left for a person.
3. Raw NVR labels are not a training set. Clean them first. The only tuning labels are human review verdicts: `person`, `pet`, `false_positive`, `uncertain`. Do not train a model yet. Tune the deterministic thresholds against cleaned labels.
4. `tracecue-engine` stays in this repository. It owns `timeline.v1` for the NVR cold archive and for offline reference exports that align radar events, cleaned NVR intervals and human verdicts. `mmwave-engine` must not import it. mmwave-fusion must not depend on it.
5. Zone-id mapping stays in the shell: a desktop channel binding, or a fusion camera config. The engine receives an already mapped `zone_id`.

## Consequences

Deleting `tracecue-engine` breaks timeline import. Feeding Hikvision XML into `mmwave-engine` couples the tracker to one camera vendor. Using uncleaned NVR labels as a teacher copies the NVR's false positives into the radar score.
