# timeline.v1 specification

[中文](timeline-v1_CN.md)

`timeline.v1` is a batch interchange document for time intervals. It is not a live sensor protocol, a video container or a fusion database dump. The machine-readable contract is [`contracts/timeline/v1/schema.json`](../../contracts/timeline/v1/schema.json).

## Document

| Field | Required | Rule |
| --- | --- | --- |
| `schema_version` | yes | Literal `timeline.v1` |
| `document_id` | yes | Unique export/document identifier |
| `source_id` | yes | Stable producer/site identity; never a secret |
| `generated_at` | yes | RFC 3339 timestamp with offset |
| `producer` | yes | Producer name and version |
| `coverage` | yes | Time range and completeness represented by this document |
| `channels` | yes | Source-local channel declarations |
| `intervals` | yes | Zero or more interval records |

`coverage.completeness` is `complete`, `partial` or `unknown`. A complete document does not imply deletion of records absent from a later import.

## Channel

`channels[].id` is stable and unique under `source_id`. `kind` identifies a broad source family such as `mmwave`, `door_contact`, `nvr_event` or `other`. `external_refs` preserve upstream identifiers without making them primary keys.

## Interval

| Field | Required | Rule |
| --- | --- | --- |
| `id` | yes | Stable under `source_id`; import idempotency key |
| `channel_id` | yes | References a declared channel |
| `event_type` | yes | Open dotted namespace, e.g. `presence.traverse` |
| `start_at`, `end_at` | yes | Explicit offset; `end_at > start_at` |
| `quality` | no | Data/trajectory quality assessment |
| `confidence` | no | 0–1 probability/confidence of event classification |
| `media_window` | no | Preferred media interval covering the event |
| `tags` | no | Portable low-cardinality labels |
| `source_ref` | no | Upstream event identity |
| `attributes` | no | Producer-namespaced extensions |

Quality and confidence are deliberately separate. Quality asks whether observations and trajectory are usable; confidence asks how strongly the producer believes the classified event occurred.

The portable `quality.score` range is 0–1. Producers using another native scale must normalize it; for example, the current Lab fusion score of 0–100 is divided by 100. A producer may preserve its raw score inside a namespaced `attributes` object.

`quality.gate` is `pass`, `fail` or `unknown`. Failed intervals can be retained for diagnostics but are excluded from the default high-confidence view.

## Event type guidance

The namespace is open. Initial recommended types are:

- `presence.traverse`
- `presence.arrival`
- `presence.departure`
- `presence.dwell`
- `zone.enter`
- `zone.exit`

Consumers must preserve unknown types and may hide unsupported behavior instead of rejecting the document.

## Import semantics

- Upsert by `(source_id, interval.id)`.
- Reject timestamps without an explicit timezone.
- Reject duplicate channel or interval IDs in one document.
- A missing old interval is not a delete instruction.
- Unmapped channels may import into a pending state but cannot produce media clips.
- Preserve original document/source references for audit.
- Resolve clock correction outside the immutable source interval; do not rewrite raw source time silently.

## Channel-to-media mapping

Source channels map to business spaces, and spaces map to one or more NVR channels:

```text
radar-hall-east → East hallway → Camera 3 (primary), Camera 7 (secondary)
```

This survives camera replacement and supports multiple views. Never map a timeline channel directly to a Hikvision `trackID` as the durable business model.
