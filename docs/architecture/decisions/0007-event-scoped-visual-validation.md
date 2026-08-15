# ADR-0007: Event-scoped local visual validation

[中文](0007-event-scoped-visual-validation_CN.md)

- Status: Accepted
- Date: 2026-08-15

## Context

Hardware validation showed that an optimized Hikvision line-crossing rule can still emit isolated false alarms whose native iVMS-4200 playback contains no crossing target. Manual review labels, temporal clustering and asking non-enthusiast users to keep tuning NVR rules do not remove this search cost. NVR-only metadata therefore cannot provide the independent evidence needed to rank these events.

The repository boundary rejects Python video decoding/rendering and a second full recording archive. The product nevertheless needs an optional local verifier that can inspect the small recording window around an already indexed NVR event without continuously scanning or retaining all recordings.

## Decision

Add event-scoped local visual validation as an optional Desktop capability:

- The NVR remains the authoritative media store and its event remains an immutable metadata bookmark.
- Analysis is requested only for an existing event and reads a bounded contextual window. It never scans a complete recording archive or runs while Desktop is closed.
- FFmpeg remains responsible for video decoding and derived WebP evidence. Python may orchestrate FFmpeg and transform a bounded, fixed-size BGR tensor for local ONNX inference; it does not implement a video codec or render frames.
- A detector and short-window tracker produce target trajectories. A deterministic geometry stage compares trajectory ground points with the evidence-backed line or polygon already read from the NVR event audit.
- Results are auxiliary evidence with explicit states: confirmed trigger, target present without a matching trigger, no supported target detected, uncertain, unavailable or failed. Negative evidence never deletes or mutates the NVR event.
- The UI may rank confirmed results first and let the user explicitly view only confirmed events. Automatic irreversible exclusion is forbidden until a separately approved, hardware-specific validation gate exists.
- Analysis runs locally. Frames, credentials and playback locators are not sent to a cloud inference service or persisted in SQLite. Cached records contain bounded summaries, model identity and optional derived evidence paths only.
- Model/runtime code and redistributed weights require separate license, provenance, hash and maintenance review. The base application continues to run when the optional model/runtime is absent.

## Consequences

TraceCue gains independent evidence for the primary event-to-trace workflow without becoming a second video archive. Event analysis adds CPU/GPU load, optional package size and new model-quality failure modes, especially at night, under glare, occlusion or compression. "No supported target detected" is weaker than a positively reconstructed crossing and must remain visibly qualified.

The first implementation is limited to line crossing and region intrusion for COCO person/vehicle classes. Every model version must be evaluated against explicitly cleared day/night hardware samples before product claims are expanded. Full-recording embeddings, general-purpose video understanding and cloud upload remain out of scope.
