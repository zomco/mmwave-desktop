# TraceCue Engine

[中文](README_CN.md)

Engine is the vendor-neutral interval core shared by Desktop import paths and Gateway producers. It is a library and contract implementation, not an end-user process.

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
