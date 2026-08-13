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
| `record_thumbnail` | Derive a one-frame JPEG from resolved playback media | Implemented, hardware-dependent |
| `event_rule_audit` | Read selected event enable/rule/trigger-link settings | Implemented, endpoint-specific |
| `camera_identification_snapshot` | Derive a cached JPEG from an evidenced low-rate track, or bounded recent recording when live permission is denied | Implemented, hardware-dependent |
| `event_hover_preview` | Derive a cached three-second animated WebP from resolved playback | Implemented, hardware-dependent |

States are `supported`, `unsupported`, `unknown` and `degraded`. Every non-unknown state records endpoint, HTTP/status outcome, parser fixture hash and observation time. Authentication failure is not evidence of unsupported capability.

## Search behavior

Recording search can be paginated and may return recording files/spans rather than the fine events visible in an official client. The adapter normalizes results but preserves raw classification and locator privately for diagnostics. It detects non-progressing pagination and enforces a result/time bound.

## Local discovery and configuration audit

TraceCue does not redistribute or reverse-engineer Hikvision's private SADP implementation. It uses the standardized ONVIF WS-Discovery probe, then a bounded unauthenticated ISAPI-candidate probe on directly attached private `/24` networks. This provides a SADP-like onboarding list but cannot promise SADP's layer-2 reach across every adapter/VLAN. Hikvision's own support page says SADP reaches end of life after April 2026 and recommends HiTools Delivery instead: [official tool notice](https://display.hikvision.com/en/support/tools/hitools/clc14d7e1a69a237dd/).

The event audit reads known motion, line-crossing, intrusion and trigger-link resources per channel/track. It parses bounded motion grids and coordinate lists into safe grid/polygon/line overlays. A denied or absent endpoint is recorded as degraded/unsupported for that model and firmware. ONVIF defines standard event and analytics operations such as `GetEventProperties`, `PullMessages`, `GetRules` and `GetSupportedRules`, but support must still be observed per device: [ONVIF operation index](https://www.onvif.org/onvif/ver20/util/operationIndex.html). A realtime subscription cannot reconstruct notifications missed while TraceCue was closed.

## Channel identity

Hikvision input IDs, stream channel IDs and RTSP track IDs are related but not interchangeable. Store each as adapter metadata under a stable internal `nvr_channel.id`. A business space maps to that internal ID, never directly to `101`-style track IDs.

Channel discovery first checks the local video-input inventory used by cameras and compatible recorders. If that endpoint is unavailable or access-controlled, NVR digital channels fall back to the read-only `/ISAPI/ContentMgmt/InputProxy/channels/status` inventory. Stream track IDs are accepted only from device evidence; they are not calculated from channel numbers.

## Authentication and transport

- Use HTTP Digest where required; never log challenge responses or authorization headers.
- Once device identity authentication succeeds, a later 401/403 from the time or channel endpoint is recorded as per-endpoint degraded evidence rather than misreported as invalid credentials.
- TLS verification policy must be explicit. Do not silently accept arbitrary certificates when HTTPS is selected.
- RTSP defaults to TCP for reliability on target LANs.
- Some recorder firmware publishes an `rtsp://` playback URI with its HTTP port
  (`80` or `443`). The adapter normalizes only those well-known HTTP ports to
  the standard RTSP port `554`; explicit non-HTTP custom RTSP ports are retained.
- Bound response sizes, XML depth, request concurrency and timeouts.

Hikvision documents `.../Streaming/channels/<channel><stream>` for live main/sub streams and compact `starttime`/`endtime` playback URLs. Tested firmware may interpret compact playback tokens as device-local wall time even though the token ends in `Z`. TraceCue keeps interval timestamps in UTC and applies the observed device UTC offset only at the FFmpeg locator boundary. This is a per-firmware behavior, not a universal timezone rule: [Hikvision RTSP URL note](https://www.hikvision.com/content/dam/hikvision/ca/bulletin/technical-bulletin/technical-article/tb_rtsp_and_http_urls_120915us.pdf), [Hikvision ISAPI search/download example](https://www.hikvisioneurope.com/eu/portal/portal/Technology%20Partner%20Program/03-How%20to/How%20to%20search%20and%20download%20the%20video%20file%20from%20NVR%20via%20ISAPI.pdf).

## Authorized hardware observation (2026-08-13)

`DS-7808NB-K1/8P` firmware `V4.30.090` exposed eight online channels with main/sub track identities, authenticated search/playback and motion configuration. Motion used an `18 × 22` hexadecimal grid map; the parser returned one bounded grid overlay instead of the prior false “0 regions.” Both documented RTSP live paths and the HTTP preview path returned 403 for the saved account, while recording search/playback remained authorized; the bounded recent-recording fallback produced a camera-identification JPEG. A cached three-second WebP and a bounded H.264 export completed. Their OSD changed from the UTC-shifted night recording to the requested daytime local hour after locator correction. Exact per-frame seek alignment and recent-snapshot freshness still depend on the recorder index and remain known hardware behaviors to measure. No customer image, address, serial or credential is stored in the repository.

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
