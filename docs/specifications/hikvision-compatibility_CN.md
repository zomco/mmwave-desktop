# 海康能力与兼容模型

[English](hikvision-compatibility.md)

“海康事件”不是一个稳定统一接口。兼容性必须按型号/固件通过实际证据判断。

## 能力键

| Key | 含义 | MVP 角色 |
| --- | --- | --- |
| `device_info` | 读取型号/固件/时间身份 | 必需 |
| `channel_discovery` | 枚举已启用媒体通道 | 必需 |
| `device_details` | 按需读取 NVR 身份及设备实际提供的摄像机连接/身份字段 | 已实现，取决于端点/固件 |
| `record_search` | 按通道/时间检索录像 Span | 必需 |
| `record_classification` | 获得粗粒度录像文件分类 | 仅作媒体回退，不作为事件来源 |
| `historical_event_search` | 查询普通/Smart 历史报警日志 | 已在有实证的 ISAPI 固件实现 |
| `realtime_event_stream` | 连接期间接收事件 | 不作为历史 MVP 来源 |
| `playback_by_uri` | 使用检索结果回放定位符 | 支持时优先 |
| `playback_by_time` | 请求通道/时间 RTSP 回放 | 备用/替代 |
| `record_thumbnail` | 从已解析回放媒体派生单帧 JPEG | 已实现，依赖硬件 |
| `event_rule_audit` | 只读部分事件启用/规则/联动配置 | 已实现，依赖端点 |
| `camera_identification_snapshot` | 从设备证据中的低码率 track 派生缓存 JPEG；实时权限被拒绝时回退有界最近录像 | 已实现，依赖硬件 |
| `event_hover_preview` | 从已解析回放派生缓存的 3 秒 WebP 动图 | 已实现，依赖硬件 |

状态为 `supported`、`unsupported`、`unknown` 和 `degraded`。除 unknown 外，每个状态记录端点、HTTP/状态结果、解析 fixture 哈希和观测时间。认证失败不等于能力不支持。

## 检索行为

录像检索可能分页，并可能返回一小时以上的连续录像文件而不是事件。因此 TraceCue 使用只读 `/ISAPI/ContentMgmt/logSearch` 报警日志建立事件书签，只在生成预览/片段时才把事件时间映射到普通录像检索。支持的归一化类型为 `motion`、`video_tamper`、`line_crossing` 和 `region_intrusion`；连续录像与模糊的 Smart 兜底标签不会成为事件筛选项。报警日志分页有界、检测不前进，并把不可信结果重新约束到所选通道/类型/时间窗；达到上限时报告截断，不保存原始日志正文。

## 局域网发现与配置审计

TraceCue 不再分发或逆向海康私有 SADP 实现。它先发送标准 ONVIF WS-Discovery 探针，再在本机直连私有 `/24` 网段执行有界、未认证的 ISAPI 候选探测。这样能提供类似 SADP 的添加列表，但不能承诺 SADP 在所有网卡/VLAN 上的二层可达性。海康官方支持页说明 SADP 在 2026 年 4 月后停止维护，并建议迁移到 HiTools Delivery：[官方工具通知](https://display.hikvision.com/en/support/tools/hitools/clc14d7e1a69a237dd/)。

事件审计按摄像机外部通道 ID 读取移动侦测/遮挡报警普通事件、越界/区域入侵 Smart 事件及 trigger-link 资源。`101` 一类码流 track ID 不能替代 Smart 规则通道 ID。解析器把有界移动栅格和坐标列表转换为安全的栅格/多边形/越界线覆盖层；设备可以返回多个入侵区域。在有实证的 4.30 固件中，LineDetection 与 FieldDetection 纵坐标都以画面底边为原点。审计 schema 4 对两者应用 `y_display = 1000 - y_device`。端点被拒绝或不存在时，按该型号/固件记录为 degraded/unknown；选择 Smart 类型时，界面隐藏缺少该能力证据的摄像机。ONVIF 定义了 `GetEventProperties`、`PullMessages`、`GetRules`、`GetSupportedRules` 等标准事件/分析操作，但仍须逐设备实测：[ONVIF operation index](https://www.onvif.org/onvif/ver20/util/operationIndex.html)。实时订阅无法重建 TraceCue 关闭期间错过的通知。

## 通道身份

海康输入 ID、码流通道 ID 和 RTSP track ID 有关联但不可互换。它们作为适配器元数据保存在稳定内部 `nvr_channel.id` 下。业务空间映射内部 ID，不直接映射 `101` 一类 track ID。

通道发现会先检查摄像机及兼容录像机使用的本机视频输入清单；该端点不可用或受权限限制时，NVR 数字通道回退到只读 `/ISAPI/ContentMgmt/InputProxy/channels/status` 清单。流 track ID 只接受设备返回的证据，不根据通道号推算。

设备详情使用 `/ISAPI/System/deviceInfo` 读取 NVR 软硬件身份，并使用输入代理状态清单读取摄像机字段。已实测固件会返回摄像机在线状态、地址、协议和端口，但即使能力资源宣称支持通道设备信息，也没有返回摄像机型号/固件。TraceCue 因此只在用户展开详情时执行读取，并把缺失的摄像机身份明确显示为不可用，不做推断。

## 认证与传输

- 按需使用 HTTP Digest，禁止记录 challenge 响应或认证头；
- 设备身份认证成功后，时间或通道端点后续返回的 401/403 应记录为该端点的降级证据，不得误报为凭据错误；
- 选择 HTTPS 时必须显式定义 TLS 校验策略，禁止静默信任任意证书；
- 目标局域网中的 RTSP 默认使用 TCP；
- 部分录像机固件会在 `rtsp://` 回放 URI 中误填 HTTP 端口（`80` 或 `443`）。
  适配器仅将这些常见 HTTP 端口归一化为标准 RTSP 端口 `554`；明确返回的其他
  自定义 RTSP 端口保持不变；
- 限制响应大小、XML 深度、请求并发和超时。

海康文档使用 `.../Streaming/channels/<channel><stream>` 表示实时主/子码流，并使用紧凑 `starttime`/`endtime` 回放 URL。TraceCue 在调用 FFmpeg 前，会把录像检索返回的宽边界替换为实际解析出的请求片段。实测部分固件会把带 `Z` 后缀的紧凑回放参数按设备本地墙上时间解释；TraceCue 随后只在此 locator 边界应用设备实测 UTC 偏移，内部/公开 Interval 时间继续使用 UTC。画面 OSD 水印由摄像机时钟生成；IPC 时间同步不健康时仍可能与 NVR 事件索引不同。这属于逐固件行为，不是通用时区规则：[海康 RTSP URL 说明](https://www.hikvision.com/content/dam/hikvision/ca/bulletin/technical-bulletin/technical-article/tb_rtsp_and_http_urls_120915us.pdf)、[海康 ISAPI 搜索/下载示例](https://www.hikvisioneurope.com/eu/portal/portal/Technology%20Partner%20Program/03-How%20to/How%20to%20search%20and%20download%20the%20video%20file%20from%20NVR%20via%20ISAPI.pdf)。

事件候选默认严格请求报警日志配对出的开始/结束区间；前后上下文改为显式可选。

## 经授权硬件观测（2026-08-13）

`DS-7808NB-K1/8P` 固件 `V4.30.090` 返回 8 个在线通道及主/子 track 身份，录像检索/回放、历史报警日志和事件配置均可认证读取。移动侦测使用 `18 × 22` 十六进制 grid map。`/ISAPI/Smart/LineDetection/1` 与 `/ISAPI/Smart/FieldDetection/1` 可读且已启用；当前启用的区域入侵使用底边原点纵坐标，而原先错误调用的 `.../101` 正是集成缺陷。通道 2 的有界越界实测在 `21:55:47Z` 返回 `lineDetectionStart`、在 `21:55:56Z` 返回 `lineDetectionStop`，证明事件时长为 9 秒。录像检索返回精确请求 UTC 范围及匹配的回放参数。导出画面 OSD 比 NVR 索引时间领先约 4 分 12 秒，由此排除 TraceCue 八小时时区转换错误，定位为摄像机/NVR 时钟未同步。增加远程预览权限前，已保存账号访问两个 RTSP 实时路径和 HTTP preview 路径时均返回 403，但录像检索/回放仍获授权；有界最近录像回退可生成摄像机识别 JPEG。设备所有者开启远程预览后，一次刷新在 1.758 秒完成，但当时仍在运行的旧后端没有记录画面来自实时路径还是回退。要形成确定的实时路径证据，仍需重启后执行带来源标签的刷新。缓存预览与 H.264 导出路径已经过硬件验证。日志保留期与结果截断仍是后续需要量化的固件行为。仓库未保存客户画面、地址、序列号、原始日志正文或凭据。

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
