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

## 已实现基线

`tracecue-hikvision` 0.1.0 提供基于标准库的 Digest 传输、显式 TLS 验证策略、有界响应读取、DTD/实体拒绝、XML 深度限制、设备/时间/通道解析、证据快照、有界录像分页、不前进检测、安全 RTSP 定位符处理和录像缺口解析。仓库内 fixture 均为合成数据，并明确不能作为硬件支持证据。

```powershell
python -m pip install -e "./integrations/hikvision[dev]"
python -m pytest integrations/hikvision/tests
```
