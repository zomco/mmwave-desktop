# 海康集成

[English](README.md)

本目录是海康 ISAPI/RTSP 行为的适配器边界。它属于 Desktop 交付，但独立放置，以免未来 ONVIF/其他品牌适配器污染领域模型。

## 适配器表面

```text
probe(connection) -> CapabilityReport
list_channels(connection) -> MediaChannel[]
search_recordings(query) -> Page<RecordingSpan>
search_intervals(query) -> Page<SourceInterval>
resolve_media(request) -> MediaResolution
```

实现必须支持 fixture 解析器、有界分页、Digest 认证、脱敏诊断和型号/固件证据。`search_intervals` 可以不支持，而 `search_recordings` 正常工作。

禁止向浏览器暴露原始回放 locator，或持久化带凭据 URL。若特定型号必须使用官方原生 SDK，应将其放入隔离 bridge 进程，而不是主 Web 进程。
