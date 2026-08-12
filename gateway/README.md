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
