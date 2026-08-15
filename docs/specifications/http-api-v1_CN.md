# HTTP API v1 草案

[English](http-api-v1.md)

所有路由同源挂载在 `/api/v1`。JSON 时间使用带明确时区的 RFC 3339。错误包含稳定机器码和安全的人类可读消息；禁止把上游响应体和凭据返回浏览器。

## 状态与设置

```text
GET    /api/v1/status
GET    /api/v1/settings
PATCH  /api/v1/settings
GET    /api/v1/diagnostics
GET    /api/v1/diagnostics/export
```

`status` 返回应用版本、schema 版本、FFmpeg 可用性和迁移/恢复状态，不得暴露文件系统秘密。

设置包含闭区间 `0..23` 内的整数 `night_start_hour` 和 `night_end_hour`。它们表示界面夜间快捷操作使用的本机墙上时钟边界；持久检索范围仍使用 UTC 毫秒，API 时间戳仍为带明确偏移的 RFC 3339。

`diagnostics` 预览支持诊断包，`diagnostics/export` 下载相同 JSON。两者都会脱敏 NVR 地址、凭据、secret 引用、Authorization header、RTSP locator、文件系统路径和原始上游 body；UI 会提示用户在分享前人工复核。

## NVR 与通道

```text
POST   /api/v1/nvrs/probe
POST   /api/v1/nvrs/discover
POST   /api/v1/nvrs
GET    /api/v1/nvrs
GET    /api/v1/nvrs/{nvr_id}
GET    /api/v1/nvrs/{nvr_id}/details
PATCH  /api/v1/nvrs/{nvr_id}
DELETE /api/v1/nvrs/{nvr_id}
POST   /api/v1/nvrs/{nvr_id}/sync-channels
GET    /api/v1/nvrs/{nvr_id}/channels
GET    /api/v1/nvrs/{nvr_id}/capabilities
GET    /api/v1/nvrs/{nvr_id}/event-audit
POST   /api/v1/nvrs/{nvr_id}/event-audit
PATCH  /api/v1/channels/{channel_id}
GET    /api/v1/channels/{channel_id}/snapshot
POST   /api/v1/channels/{channel_id}/snapshot
GET    /api/v1/channels/{channel_id}/snapshot/content
```

`nvrs/discover` 接受 0.5 到 5.0 秒的有界 `timeout_seconds`。它优先使用 ONVIF WS-Discovery，回退方案只在最多三个本机直连私有 `/24` 网段上进行未认证的 80 端口探测。回退结果只是 ISAPI 候选，必须由用户提供凭据通过 `nvrs/probe` 后才能添加。`nvrs/{nvr_id}/details` 在用户展开详情时按需执行只读身份读取，返回 NVR 软硬件字段和设备实际提供的摄像机连接/身份字段；NVR 不支持的摄像机型号或固件明确返回 `null`，绝不返回凭据或原始 XML。事件审计 schema `4` 按摄像机外部通道 ID 只读移动/遮挡普通事件与越界/区域入侵 Smart 事件；在有实测证据时返回有界栅格/多边形/越界线覆盖层，禁止返回原始 XML/凭据，也绝不修改 NVR。Schema 4 把有实证的 LineDetection 与 FieldDetection 底边原点纵坐标归一化为浏览器左上原点坐标。旧缓存审计在首次访问时进行一次只读刷新。通道截图异步生成，优先使用设备证据中的低码率 track；实时查看权限被拒绝时，回退到有界的最近录像检索。已验证截图在十分钟内保持新鲜；过期后 POST 会立即返回旧缓存，同时只启动一个后台刷新，并通过 `stale`、`refreshing` 明确状态。两个有界作业线程最多并发两个任务，并优先处理检索/导出而不是排队中的摄像机刷新。回退画面仍只用于识别摄像机，不宣称是实时视频。

截图状态还会返回 `source=live_low_rate|recent_recording|null`，用于记录已完成刷新的来源路径，但不暴露 RTSP locator 或凭据。

Probe 只读并返回结构化证据：

```json
{
  "reachable": true,
  "authenticated": true,
  "device": { "model": "redacted-example", "firmware": "v0" },
  "clock": {
    "observed_at": "2026-08-12T08:00:00Z",
    "estimated_skew_ms": -47000,
    "timezone": "+08:00"
  },
  "capabilities": {
    "record_search": "supported",
    "record_classification": "supported",
    "historical_event_search": "unknown",
    "realtime_event_stream": "unsupported",
    "playback_by_uri": "supported"
  },
  "warnings": [
    { "code": "CLOCK_SKEW", "message": "设备时间与本机存在偏差。" }
  ]
}
```

能力状态为 `supported`、`unsupported`、`unknown` 和 `degraded`。端点/状态证据由服务端另存，不直接进入公开响应。

删除 NVR 会清除其受保护凭据引用、能力、通道、NVR 来源索引及本地派生片段，但绝不会修改 NVR 上保存的原始录像。

## 检索与书签

```text
POST /api/v1/search-jobs
GET  /api/v1/search-jobs/{job_id}
GET  /api/v1/search-jobs/{job_id}/results
GET  /api/v1/search-presets
POST /api/v1/search-presets
DELETE /api/v1/search-presets/{preset_id}
GET  /api/v1/trace-sessions
POST /api/v1/trace-sessions
GET  /api/v1/trace-sessions/{session_id}
DELETE /api/v1/trace-sessions/{session_id}
POST /api/v1/trace-sessions/{session_id}/iterations
GET  /api/v1/trace-sessions/{session_id}/results
PATCH /api/v1/trace-sessions/{session_id}/events/{bookmark_id}
GET  /api/v1/bookmarks
GET  /api/v1/bookmarks/{bookmark_id}
GET  /api/v1/bookmarks/{bookmark_id}/preview
POST /api/v1/bookmarks/{bookmark_id}/preview
GET  /api/v1/bookmarks/{bookmark_id}/preview/content
GET  /api/v1/bookmarks/{bookmark_id}/animation
POST /api/v1/bookmarks/{bookmark_id}/animation
GET  /api/v1/bookmarks/{bookmark_id}/animation/content
GET  /api/v1/bookmarks/{bookmark_id}/visual-analysis
POST /api/v1/bookmarks/{bookmark_id}/visual-analysis
```

请求示例：

```json
{
  "nvr_id": "nvr_01",
  "channel_ids": ["channel_01"],
  "from": "2026-08-12T00:00:00+08:00",
  "to": "2026-08-13T00:00:00+08:00",
  "source_modes": ["historical_event_log"],
  "event_types": ["line_crossing"],
  "preset_id": "preset_01"
}
```

实际目标区域恰好是一个稳定摄像机 ID；浏览器按 NVR 分组并用单选方式展示摄像机画面，因此不再提供录像机或自由文本区域筛选。`channel_ids` 必须恰好有一项。`event_types` 也必须恰好包含 `motion`、`video_tamper`、`line_crossing` 或 `region_intrusion` 中的一项；连续录像、Smart 兜底标签和多事件类型请求都会被拒绝。Preset 保存一个摄像机 ID 与一个事件标签。作业读取有界历史报警日志，并在同摄像机、同类型、最长一小时范围内配对开始/停止条目。有配对时保存真实 `event_duration_ms`；无法配对时保存 `null` 及 `duration_source: "unknown"`。`result.truncated` 表示适配器达到上限。只有生成预览/片段时才执行录像检索。`search-jobs/{job_id}/results?limit=12&offset=0` 返回有界分页、总数和 `has_more`，且只包含本次检索产生的事件。JPEG 预览异步生成并按事件缓存；预览和动图状态响应包含 `0` 到 `1` 的归一化作业 `progress`，它表示处理阶段而非上游字节计数；动图路由按需生成经过校验的有界 3 秒 WebP 悬停预览。全部文件均在派生媒体根目录原子写入。

视觉分析是可选能力，目前只接受 `line_crossing` 和 `region_intrusion` 书签。分析处于排队、运行或就绪时，POST 保持幂等。它解析最长 30 秒的上下文窗口，由 FFmpeg 输出固定尺寸 BGR 帧，使用已配置的本地 ONNX 检测器识别并跟踪支持的行人/车辆目标，再把目标落地轨迹与缓存中已有实证的规则线/多边形进行比较。缓存响应返回 `confirmed_trigger`、`target_present_no_trigger`、`no_supported_target_detected` 或 `uncertain`，并包含模型身份、分析时间窗、可选视觉触发时刻和阶段进度。负面证据绝不修改或删除 NVR 书签。确认触发时，可以把悬停 WebP 原子替换为以重建触发时刻为中心的短证据窗口。

Trace 会话持久保存一个摄像机/事件类型范围，并只接受一个有界时间迭代。先用 `{"channel_ids":["channel_01"],"event_types":["motion"]}` 创建会话，再追加 `{"from":"2026-08-12T18:00:00+08:00","to":"2026-08-13T06:00:00+08:00","label":"时间范围"}`。重复相同时间窗保持幂等；第二个不同时间窗返回 `TRACE_SESSION_WINDOW_FIXED`，客户端必须新建检索。为保持 schema 兼容，持久化作业 kind 仍是 `recording_search`，但事件来源已经是历史报警日志。

`trace-sessions/{session_id}/results` 接受有界 `limit`/`offset`、`review_state=active|all|unreviewed|reviewed|excluded|candidate`、可选成对 RFC 3339 `from`/`to`、`duration_class=unknown|under_5s|5_to_30s|over_30s`、包含边界的精确 `min_duration_ms`/`max_duration_ms`、`activity_mode=all|isolated|clustered` 及 `summary_only`。某事件与此前事件累计结束点的间隔不超过 30 秒时归入同一稳定活动簇；只有一个事件的是 `isolated`，多个事件的是 `clustered`。响应始终包含全局审阅计数、最多 2000 个逐事件 `timeline` 区间（`id`、`start_at`、`end_at`、可空 `duration_ms`、`cluster_size`）、`timeline_truncated`、当前 `selected_window`、`duration_buckets`、`duration_range`、`activity_counts` 和 `activity_cluster_gap_ms`。时间筛选使用区间重叠语义；时长/活动统计按所选子时间窗动态重算，时长统计还会先应用活动模式，再应用具体时长边界。`summary_only=true` 时 `items` 为空且不会触发预览工作；普通响应返回过滤分页及生成候选片段所需的作业身份。`active` 只排除明确标为 `excluded` 的事件。审阅 PATCH 按会话持久保存审阅状态。会话记录只含稳定 ID 和事件标签，绝不包含凭据、Authorization header 或回放 locator。

大范围检索使用后台作业。书签列表使用服务端不透明 cursor，禁止透传海康分页位置或 token。

## Clip 与作业

```text
POST   /api/v1/clips
GET    /api/v1/clips
GET    /api/v1/clips/{clip_id}
GET    /api/v1/clips/{clip_id}/content
POST   /api/v1/clips/{clip_id}/share
DELETE /api/v1/clips/{clip_id}
GET    /api/v1/jobs
GET    /api/v1/jobs/{job_id}
POST   /api/v1/jobs/{job_id}/cancel
```

按书签或显式通道/时间窗创建，禁止接受浏览器传入的 RTSP URL：

```json
{
  "bookmark_id": "interval_01",
  "search_job_id": "job_search_01",
  "window_override": { "pre_roll_ms": 0, "post_roll_ms": 0 },
  "audio_policy": "prefer"
}
```

按书签创建时，默认行为和事件检索界面都严格按索引事件开始/结束区间导出（`pre_roll_ms=0`、`post_roll_ms=0`），不隐式限制时长。非零上下文缓冲继续作为显式 API/设置选项。公开 Clip 记录包含安全的 `origin` 字段：书签 ID、检索作业 ID、区域标签、通道标签、事件类型/原始分类、事件时间窗、`time_basis: "nvr_index"`、是否裁剪了显式请求的相邻事件上下文，以及是否应用了显式候选时长上限。同一摄像机/检索中的相邻非重叠事件只在仍位于事件间隙内的整秒中点裁剪非零前后上下文；事件本体绝不会被裁掉，真实事件本体重叠仍保留重叠。响应绝不包含 RTSP locator 或凭据。显式通道/时间窗出片的 `origin` 为 `null`。Clip 记录包含阶段 `progress`；浏览器在下载就绪 MP4 时另外计算实际字节进度。

`clips/{clip_id}/share` 是受 ADR-0006 约束的本机用户显式操作。它启动或复用独立的私有网卡监听器，返回本地生成的能力 URL 及过期时间。一个仅存内存的 256 位令牌在 15 分钟内只允许通过 `GET`/`HEAD` 访问极简页面和这一条已就绪片段的有界 Range 内容；不会暴露回环 API、NVR 地址、凭据或文件路径。二维码完全在本地生成，URL 不会发送给第三方二维码服务。

内部事件与 Clip 时间继续使用 UTC。进入 FFmpeg 前，先把每个 locator 的宽录像范围替换为实际解析出的请求媒体片段边界。对于经实测会把紧凑 RTSP 回放参数当作设备本地墙上时间解释（尽管带 `Z` 后缀）的海康固件，媒体边界随后只使用实测设备偏移转换这些参数；公开事件/Clip 时间戳不做平移。画面内摄像机 OSD 水印使用摄像机自身时钟，可能与 NVR 索引事件时间不同；TraceCue 会说明差异，而不是猜测校正。

`audio_policy` 可取 `prefer`、`preserve` 或 `omit`。`prefer` 会将受支持音频转为
AAC；若 NVR 声明了 FFmpeg 无法解码的私有音频载荷，则降级生成静音片段。
`preserve` 为严格模式，不会静默丢弃音频。渲染前会先检查源视频编码：H.264
尽量直接封装，其他编码转换为适合浏览器播放的 H.264。

作业状态为 `queued`、`running`、`succeeded`、`failed`、`cancelled` 和 `interrupted`。重启时原 `running` 作业变为 `interrupted`，恢复必须作为显式新尝试。Clip content 支持有边界的 HTTP Range。

## Timeline 导入与映射

```text
POST /api/v1/timeline-imports/inspect
GET  /api/v1/timeline-imports/{import_id}
POST /api/v1/timeline-imports/{import_id}/commit
GET  /api/v1/sources
GET  /api/v1/source-channels
PUT  /api/v1/source-channels/{source_channel_id}/binding
```

Inspect 在不修改 Interval 表的情况下校验 schema、ID、时间和映射。Commit 引用已检查内容哈希并保持幂等。未映射通道可以存储，但不能请求出片。

## 错误结构

```json
{
  "error": {
    "code": "RECORDING_GAP",
    "message": "NVR 未完整覆盖请求时间窗。",
    "request_id": "req_01",
    "details": { "coverage": "partial" }
  }
}
```

初始稳定错误族：`AUTH_*`、`NVR_*`、`CAPABILITY_*`、`CLOCK_*`、`TIMELINE_*`、`MAPPING_*`、`RECORDING_*`、`MEDIA_*`、`STORAGE_*` 和 `JOB_*`。
