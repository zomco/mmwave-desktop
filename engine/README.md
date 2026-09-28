# TraceCue Engine

[中文](README_CN.md)

Engine (`tracecue-engine`) is the vendor-neutral interval library for Desktop import paths and Gateway producers. It is not an end-user process, and it is not the radar tracker. The highest-weight video tag is the separate `mmwave-engine` package ([ADR-0009](../docs/architecture/decisions/0009-radar-tag-outranks-nvr.md)).

This library may later export an offline `timeline.v1` reference that aligns radar events, cleaned NVR intervals and human review verdicts. Raw NVR labels are not that reference. `mmwave-engine` must not import this package.

## Owns

- Source/channel/interval value types.
- Timestamp and invariant validation.
- Deterministic identity and idempotent merge primitives.
- Quality-gate result representation.
- Interval merge/filter and `media_window` calculation.
- `timeline.v1` reading, writing and schema compatibility.

## Dependency rule

Engine has no dependency on Desktop, Gateway, Hikvision, FFmpeg, Home Assistant or OS credential stores. Domain logic must be deterministic under a provided clock/ID strategy and testable without hardware.

## Versioning

The JSON contract uses `timeline.v1`. Library releases follow SemVer once external consumers exist. Backward-compatible readers may accept additive fields only when the schema/version policy explicitly allows them.

## First executable slice

Validate the checked-in example, reject invalid timezone/range/channel references, and prove idempotent import by `(source_id, interval.id)`.

## Implemented baseline

`tracecue-engine` 0.1.0 implements immutable timeline value types, strict and size-bounded `timeline.v1` reading/writing, explicit-offset timestamps, deterministic IDs, quality-gate results, media windows, filtering, deterministic merge and idempotent upsert primitives. It has no Desktop, Gateway, Hikvision, FFmpeg or HA dependency.

```powershell
python -m pip install -e "./engine[dev]"
python -m pytest engine/tests
```
