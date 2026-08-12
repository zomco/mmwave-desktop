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
```

`nvrs/discover` 接受 0.5 到 5.0 秒的有界 `timeout_seconds`。它优先使用 ONVIF WS-Discovery，回退方案只在最多三个本机直连私有 `/24` 网段上进行未认证的 80 端口探测。回退结果只是 ISAPI 候选，必须由用户提供凭据通过 `nvrs/probe` 后才能添加。事件审计只读部分移动/智能规则与 trigger-link 配置；仅返回安全摘要，禁止返回原始 XML/凭据，也绝不修改 NVR。

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
GET  /api/v1/bookmarks
GET  /api/v1/bookmarks/{bookmark_id}
GET  /api/v1/bookmarks/{bookmark_id}/preview
POST /api/v1/bookmarks/{bookmark_id}/preview
GET  /api/v1/bookmarks/{bookmark_id}/preview/content
```

请求示例：

```json
{
  "nvr_id": "nvr_01",
  "channel_ids": ["channel_01"],
  "from": "2026-08-12T00:00:00+08:00",
  "to": "2026-08-13T00:00:00+08:00",
  "source_modes": ["record_classification"],
  "area_name": "北门",
  "event_types": ["motion", "line_crossing"],
  "preset_id": "preset_01"
}
```

`area_name` 是用户定义的业务标签；实际区域映射由所选稳定摄像机 ID 和事件类型标签组成，不能声称它等于 NVR 画面多边形。Preset 保存该映射。`search-jobs/{job_id}/results` 只返回本次检索产生的事件，使后续片段能够精确追溯到检索会话。预览生成是异步 FFmpeg 作业，在派生媒体根目录下原子写入一张校验后的 JPEG。

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
