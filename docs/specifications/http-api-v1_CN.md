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
POST   /api/v1/nvrs
GET    /api/v1/nvrs
GET    /api/v1/nvrs/{nvr_id}
PATCH  /api/v1/nvrs/{nvr_id}
DELETE /api/v1/nvrs/{nvr_id}
POST   /api/v1/nvrs/{nvr_id}/sync-channels
GET    /api/v1/nvrs/{nvr_id}/channels
GET    /api/v1/nvrs/{nvr_id}/capabilities
PATCH  /api/v1/channels/{channel_id}
```

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

## 检索与书签

```text
POST /api/v1/search-jobs
GET  /api/v1/search-jobs/{job_id}
GET  /api/v1/bookmarks
GET  /api/v1/bookmarks/{bookmark_id}
```

请求示例：

```json
{
  "nvr_id": "nvr_01",
  "channel_ids": ["channel_01"],
  "from": "2026-08-12T00:00:00+08:00",
  "to": "2026-08-13T00:00:00+08:00",
  "source_modes": ["record_classification", "historical_event"]
}
```

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
  "window_override": { "pre_roll_ms": 5000, "post_roll_ms": 10000 },
  "audio_policy": "prefer"
}
```

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
