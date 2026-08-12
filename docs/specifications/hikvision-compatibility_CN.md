# 海康能力与兼容模型

[English](hikvision-compatibility.md)

“海康事件”不是一个稳定统一接口。兼容性必须按型号/固件通过实际证据判断。

## 能力键

| Key | 含义 | MVP 角色 |
| --- | --- | --- |
| `device_info` | 读取型号/固件/时间身份 | 必需 |
| `channel_discovery` | 枚举已启用媒体通道 | 必需 |
| `record_search` | 按通道/时间检索录像 Span | 必需 |
| `record_classification` | 获得 `motion`/`smart` 类粗分类 | 可选增强 |
| `historical_event_search` | 查询细颗粒历史智能事件 | 型号专有增强 |
| `realtime_event_stream` | 连接期间接收事件 | 不作为历史 MVP 来源 |
| `playback_by_uri` | 使用检索结果回放定位符 | 支持时优先 |
| `playback_by_time` | 请求通道/时间 RTSP 回放 | 备用/替代 |
| `record_thumbnail` | 从已解析回放媒体派生单帧 JPEG | 已实现，依赖硬件 |
| `event_rule_audit` | 只读部分事件启用/规则/联动配置 | 已实现，依赖端点 |

状态为 `supported`、`unsupported`、`unknown` 和 `degraded`。除 unknown 外，每个状态记录端点、HTTP/状态结果、解析 fixture 哈希和观测时间。认证失败不等于能力不支持。

## 检索行为

录像检索可能分页，返回的也可能是录像文件/Span，而不是官方客户端可见的精细事件。适配器归一化结果，但私下保留原始分类和 locator 用于诊断。必须检测不前进的分页并限制结果数和总耗时。

## 局域网发现与配置审计

TraceCue 不再分发或逆向海康私有 SADP 实现。它先发送标准 ONVIF WS-Discovery 探针，再在本机直连私有 `/24` 网段执行有界、未认证的 ISAPI 候选探测。这样能提供类似 SADP 的添加列表，但不能承诺 SADP 在所有网卡/VLAN 上的二层可达性。海康官方支持页说明 SADP 在 2026 年 4 月后停止维护，并建议迁移到 HiTools Delivery：[官方工具通知](https://display.hikvision.com/en/support/tools/hitools/clc14d7e1a69a237dd/)。

事件审计按通道/track 读取已知的移动侦测、越界、区域入侵与 trigger-link 资源。端点被拒绝或不存在时，按该型号/固件记录为 degraded/unsupported。ONVIF 定义了 `GetEventProperties`、`PullMessages`、`GetRules`、`GetSupportedRules` 等标准事件/分析操作，但仍须逐设备实测：[ONVIF operation index](https://www.onvif.org/onvif/ver20/util/operationIndex.html)。实时订阅无法重建 TraceCue 关闭期间错过的通知。

## 通道身份

海康输入 ID、码流通道 ID 和 RTSP track ID 有关联但不可互换。它们作为适配器元数据保存在稳定内部 `nvr_channel.id` 下。业务空间映射内部 ID，不直接映射 `101` 一类 track ID。

通道发现会先检查摄像机及兼容录像机使用的本机视频输入清单；该端点不可用或受权限限制时，NVR 数字通道回退到只读 `/ISAPI/ContentMgmt/InputProxy/channels/status` 清单。流 track ID 只接受设备返回的证据，不根据通道号推算。

## 认证与传输

- 按需使用 HTTP Digest，禁止记录 challenge 响应或认证头；
- 设备身份认证成功后，时间或通道端点后续返回的 401/403 应记录为该端点的降级证据，不得误报为凭据错误；
- 选择 HTTPS 时必须显式定义 TLS 校验策略，禁止静默信任任意证书；
- 目标局域网中的 RTSP 默认使用 TCP；
- 部分录像机固件会在 `rtsp://` 回放 URI 中误填 HTTP 端口（`80` 或 `443`）。
  适配器仅将这些常见 HTTP 端口归一化为标准 RTSP 端口 `554`；明确返回的其他
  自定义 RTSP 端口保持不变；
- 限制响应大小、XML 深度、请求并发和超时。

## 兼容记录

每个测试组合记录：

```text
型号、固件，已知时含区域/系列
HTTP/HTTPS 和 RTSP 端口
通道数量和 ID 示例
含脱敏 fixture 的能力结果
录像视频/音频编码
H.264 remux 结果
H.265/音频转码结果
时钟偏差/时区行为
已知缺口和复现说明
```

只有可重复通过出片测试的组合才能称为“支持”；其他组合保持实验性或未知。
