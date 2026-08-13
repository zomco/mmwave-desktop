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

`nvrs/discover` 接受 0.5 到 5.0 秒的有界 `timeout_seconds`。它优先使用 ONVIF WS-Discovery，回退方案只在最多三个本机直连私有 `/24` 网段上进行未认证的 80 端口探测。回退结果只是 ISAPI 候选，必须由用户提供凭据通过 `nvrs/probe` 后才能添加。事件审计 schema `2` 按摄像机外部通道 ID 只读移动/遮挡普通事件与越界/区域入侵 Smart 事件；在有实测证据时返回有界栅格/多边形/越界线覆盖层，禁止返回原始 XML/凭据，也绝不修改 NVR。旧缓存审计在首次访问时进行一次只读刷新。通道截图异步生成，优先使用设备证据中的低码率 track；实时查看权限被拒绝时，回退到有界的最近录像检索。截图 30 秒过期并只从本地派生媒体缓存交付；回退画面只用于识别摄像机，不宣称是实时视频。

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
```

请求示例：

```json
{
  "nvr_id": "nvr_01",
  "channel_ids": ["channel_01"],
  "from": "2026-08-12T00:00:00+08:00",
  "to": "2026-08-13T00:00:00+08:00",
  "source_modes": ["historical_event_log"],
  "event_types": ["motion", "line_crossing"],
  "preset_id": "preset_01"
}
```

实际目标区域是所选稳定摄像机 ID 集合；浏览器按 NVR 分组展示摄像机画面，因此不再提供录像机或自由文本区域筛选。`event_types` 只接受 `motion`、`video_tamper`、`line_crossing`、`region_intrusion`，空列表表示四类全部检索；连续录像与 Smart 兜底标签会被拒绝。Preset 保存摄像机 ID 与事件标签并可跨多台录像机；前端会为涉及的每台 NVR 提交一个有界检索作业。作业读取有界历史报警日志，以稳定 ID 保存一秒事件书签；`result.truncated` 表示适配器达到上限。只有生成预览/片段时才执行录像检索，把书签时间映射到媒体。`search-jobs/{job_id}/results?limit=12&offset=0` 返回有界分页、总数和 `has_more`，且只包含本次检索产生的事件。JPEG 预览异步生成并按事件缓存；动图路由按需生成经过校验的有界 3 秒 WebP 悬停预览。全部文件均在派生媒体根目录原子写入。

Trace 会话持久保存一组摄像机/事件类型范围，并包含一个或多个有界时间迭代。先用 `{"channel_ids":["channel_01"],"event_types":["motion"]}` 创建会话，再追加 `{"from":"2026-08-12T18:00:00+08:00","to":"2026-08-13T06:00:00+08:00","label":"昨晚"}` 时间窗。对同一会话重复相同时间窗保持幂等。涉及的每台 NVR 继续获得独立作业（为保持 schema 兼容，持久化 kind 仍是 `recording_search`，但事件来源已经是历史报警日志）；会话结果使用稳定 Interval ID 跨迭代累积去重。

`trace-sessions/{session_id}/results` 接受有界 `limit`/`offset`、`review_state=active|all|unreviewed|reviewed|excluded|candidate`，以及可选且必须成对出现的 RFC 3339 `from`/`to` 结果聚焦范围。响应返回全局审阅状态计数、UTC 小时密度桶、过滤后的分页和生成候选片段所需的检索作业身份。`active` 只排除明确标为 `excluded` 的事件。审阅 PATCH 按会话持久保存 `unreviewed`、`reviewed`、`excluded` 或 `candidate`；设为 `unreviewed` 会删除显式审阅记录。会话记录只含稳定 ID 和事件标签，绝不包含凭据、Authorization header 或回放 locator。删除 NVR 时也会删除摄像机范围引用该 NVR 的 Trace 会话。

大范围检索使用后台作业。书签列表使用服务端不透明 cursor，禁止透传海康分页位置或 token。

## Clip 与作业

```text
POST   /api/v1/clips
GET    /api/v1/clips
GET    /api/v1/clips/{clip_id}
GET    /api/v1/clips/{clip_id}/content
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
  "window_override": { "pre_roll_ms": 5000, "post_roll_ms": 10000, "max_duration_ms": 30000 },
  "audio_policy": "prefer"
}
```

按书签创建时，公开 Clip 记录包含安全的 `origin` 字段：书签 ID、检索作业 ID、区域标签、通道标签、事件类型/原始分类、事件时间窗，以及是否应用了显式候选时长上限；绝不包含 RTSP locator 或凭据。显式通道/时间窗出片的 `origin` 为 `null`。

内部事件与 Clip 时间继续使用 UTC。对于经实测会把紧凑 RTSP 回放参数当作设备本地墙上时间解释（尽管带 `Z` 后缀）的海康固件，媒体边界仅使用实测设备偏移转换这些 locator 参数；公开事件/Clip 时间戳不做平移。

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
