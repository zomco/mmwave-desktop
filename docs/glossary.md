# Glossary

[中文](glossary_CN.md)

| Term | Meaning in TraceCue |
| --- | --- |
| Bookmark | Reviewable metadata interval pointing toward NVR media |
| Clip | Derived short media file exported from NVR recording |
| Interval | Typed time range with source, channel and optional quality metadata |
| Media window | Preferred pre/post-roll range used to resolve recording |
| NVR candidate | Bookmark derived from NVR recording/event metadata; not inherently high confidence |
| High-confidence timeline | Independently quality-gated interval source, e.g. validated radar trajectory |
| Space | Business location that connects source channels to one or more camera views |
| Recording span | NVR-reported interval where media exists, with an adapter-private locator |
| Capability evidence | Model/firmware-specific observation supporting a capability state |
| Gateway | Always-on source collector and interval producer |
| Engine | Vendor-neutral interval/quality contract library |
| Lab | Existing `mmwave-*` research repositories; not product runtime dependencies |
