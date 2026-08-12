# TraceCue Gateway

[中文](README_CN.md)

Gateway is the always-on timeline producer for sensor-backed deployments. It is a companion component under the TraceCue product, not a separately marketed application in the initial phase.

## Owns

- Continuous device acquisition and reconnect policy.
- Adapter/model identity and source clock health.
- Bounded raw diagnostics and optional short trajectory buffer.
- Engine invocation, quality decisions and durable interval delivery.
- Local export/synchronization using the versioned timeline contract.

## Does not own

- NVR credentials, recording searches or FFmpeg media export.
- Desktop UI/business workflows.
- Home Assistant as a required runtime.

## Productization rule

The laboratory repositories provide protocol, calibration and quality knowledge. Product gateway code must be independently buildable and support a certified hardware subset. "Supported by the Lab" does not imply commercially certified hardware.

## First executable slice

One certified 2D radar/model runs unattended, maintains clock health, emits a deterministic `presence.traverse` interval and preserves it while Desktop is offline.

## Implemented baseline

`tracecue-gateway` 0.1.0 implements a bounded experimental JSON-line TCP acquisition surface, reconnect backoff, rolling source-clock health, bounded short-track state, deterministic traverse intervals, quality gates, bounded diagnostics, SQLite durability and `timeline.v1` export. Fixture tests prove intervals survive while Desktop is offline.

```powershell
python -m pip install -e ./engine -e "./gateway[dev]"
python -m pytest gateway/tests
```

No physical radar/model has been certified. The JSON-line adapter is explicitly experimental; a supported hardware adapter requires protocol fixtures, license/provenance review and repeatable unattended hardware evidence.
