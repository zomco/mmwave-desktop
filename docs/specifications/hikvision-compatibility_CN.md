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
| `camera_identification_snapshot` | 从设备证据中的低码率 track 派生缓存 JPEG；实时权限被拒绝时回退有界最近录像 | 已实现，依赖硬件 |
| `event_hover_preview` | 从已解析回放派生缓存的 3 秒 WebP 动图 | 已实现，依赖硬件 |

状态为 `supported`、`unsupported`、`unknown` 和 `degraded`。除 unknown 外，每个状态记录端点、HTTP/状态结果、解析 fixture 哈希和观测时间。认证失败不等于能力不支持。

## 检索行为

录像检索可能分页，返回的也可能是录像文件/Span，而不是官方客户端可见的精细事件。适配器归一化结果，但私下保留原始分类和 locator 用于诊断。必须检测不前进的分页并限制结果数和总耗时。

## 局域网发现与配置审计

TraceCue 不再分发或逆向海康私有 SADP 实现。它先发送标准 ONVIF WS-Discovery 探针，再在本机直连私有 `/24` 网段执行有界、未认证的 ISAPI 候选探测。这样能提供类似 SADP 的添加列表，但不能承诺 SADP 在所有网卡/VLAN 上的二层可达性。海康官方支持页说明 SADP 在 2026 年 4 月后停止维护，并建议迁移到 HiTools Delivery：[官方工具通知](https://display.hikvision.com/en/support/tools/hitools/clc14d7e1a69a237dd/)。

事件审计按通道/track 读取已知的移动侦测、越界、区域入侵与 trigger-link 资源，并把有界移动栅格和坐标列表解析成安全的栅格/多边形/越界线覆盖层。端点被拒绝或不存在时，按该型号/固件记录为 degraded/unsupported。ONVIF 定义了 `GetEventProperties`、`PullMessages`、`GetRules`、`GetSupportedRules` 等标准事件/分析操作，但仍须逐设备实测：[ONVIF operation index](https://www.onvif.org/onvif/ver20/util/operationIndex.html)。实时订阅无法重建 TraceCue 关闭期间错过的通知。

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

海康文档使用 `.../Streaming/channels/<channel><stream>` 表示实时主/子码流，并使用紧凑 `starttime`/`endtime` 回放 URL。实测部分固件会把带 `Z` 后缀的紧凑回放参数按设备本地墙上时间解释。TraceCue 继续用 UTC 保存 Interval，只在 FFmpeg locator 边界应用设备实测 UTC 偏移；这属于逐固件行为，不是通用时区规则：[海康 RTSP URL 说明](https://www.hikvision.com/content/dam/hikvision/ca/bulletin/technical-bulletin/technical-article/tb_rtsp_and_http_urls_120915us.pdf)、[海康 ISAPI 搜索/下载示例](https://www.hikvisioneurope.com/eu/portal/portal/Technology%20Partner%20Program/03-How%20to/How%20to%20search%20and%20download%20the%20video%20file%20from%20NVR%20via%20ISAPI.pdf)。

## 经授权硬件观测（2026-08-13）

`DS-7808NB-K1/8P` 固件 `V4.30.090` 返回 8 个在线通道及主/子 track 身份，录像检索/回放和移动侦测配置均可认证读取。移动侦测使用 `18 × 22` 十六进制 grid map；解析器现返回一个有界栅格覆盖层，不再错误显示“0 区域”。已保存账号访问两个已记录 RTSP 实时路径和 HTTP preview 路径时均返回 403，但录像检索/回放仍获授权；有界最近录像回退成功生成摄像机识别 JPEG。缓存的 3 秒 WebP 与有界 H.264 导出均已完成；修正 locator 后，其 OSD 已从偏到 UTC 夜间的录像恢复到用户请求的白天本地小时。精确逐帧 seek 和最近截图新鲜度仍受录像机索引影响，属于后续需要量化的硬件行为。仓库未保存客户画面、地址、序列号或凭据。

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
