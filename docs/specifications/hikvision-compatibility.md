# Hikvision capability and compatibility model

[中文](hikvision-compatibility_CN.md)

"Hikvision events" is not one stable interface. Compatibility is assessed per model and firmware using observed evidence.

## Capability keys

| Key | Meaning | MVP role |
| --- | --- | --- |
| `device_info` | Read model/firmware/time identity | Required |
| `channel_discovery` | Enumerate enabled media channels | Required |
| `record_search` | Search recorded spans by channel/time | Required |
| `record_classification` | Receive coarse `motion`/`smart`-like classification | Optional enhancement |
| `historical_event_search` | Query fine historical smart events | Model-specific enhancement |
| `realtime_event_stream` | Receive events while connected | Not a historical MVP source |
| `playback_by_uri` | Consume a search-result playback locator | Preferred where supported |
| `playback_by_time` | Request channel/time RTSP playback | Fallback/alternative |
| `record_thumbnail` | Fetch a recording thumbnail | Deferred |

States are `supported`, `unsupported`, `unknown` and `degraded`. Every non-unknown state records endpoint, HTTP/status outcome, parser fixture hash and observation time. Authentication failure is not evidence of unsupported capability.

## Search behavior

Recording search can be paginated and may return recording files/spans rather than the fine events visible in an official client. The adapter normalizes results but preserves raw classification and locator privately for diagnostics. It detects non-progressing pagination and enforces a result/time bound.

## Channel identity

Hikvision input IDs, stream channel IDs and RTSP track IDs are related but not interchangeable. Store each as adapter metadata under a stable internal `nvr_channel.id`. A business space maps to that internal ID, never directly to `101`-style track IDs.

## Authentication and transport

- Use HTTP Digest where required; never log challenge responses or authorization headers.
- TLS verification policy must be explicit. Do not silently accept arbitrary certificates when HTTPS is selected.
- RTSP defaults to TCP for reliability on target LANs.
- Bound response sizes, XML depth, request concurrency and timeouts.

## Compatibility record

Each tested combination records:

```text
model, firmware, region/series if known
HTTP/HTTPS and RTSP ports
channel count and ID examples
capability outcomes with redacted fixtures
recording codecs/audio codecs
H.264 remux result
H.265/audio transcode result
clock skew/timezone behavior
known gaps and reproduction notes
```

Only combinations with a repeatable clip test can be described as supported. Others remain experimental or unknown.
