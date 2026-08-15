# 数据模型草案

[English](data-model.md)

Desktop 初期使用 SQLite。表使用稳定不透明文本 ID 和 UTC epoch 毫秒；密钥只保存引用，不保存正文。

| 表 | 关键字段 | 用途 |
| --- | --- | --- |
| `nvrs` | `id`、主机/端口、型号、固件、时区、时钟偏差、`secret_ref` | 设备身份和凭据引用 |
| `nvr_capabilities` | `nvr_id`、能力、状态、证据、观测时间 | 有证据的兼容性快照 |
| `nvr_channels` | `id`、`nvr_id`、外部 ID、track ID、设备名、别名、在线状态 | 稳定媒体通道身份 |
| `sources` | `id`、kind、外部来源 ID、版本 | NVR、导入文件、gateway 或其他生产者 |
| `source_channels` | `id`、`source_id`、外部 key、标签、kind | 生产者内部通道身份 |
| `spaces` | `id`、名称 | 房间、走廊等业务位置 |
| `space_media_channels` | 空间、NVR 通道、角色、优先级、有效期 | 一个空间对应一个或多个视角 |
| `source_channel_bindings` | 来源通道、空间、有效期、校正策略 | 传感器/来源通道到业务空间 |
| `intervals` | 来源/事件身份、通道、类型、原始/解析时间、质量、媒体窗口 | 持久书签索引 |
| `recording_spans` | NVR 通道、时间范围、分类、locator、观测/过期时间 | 可刷新 NVR 录像覆盖缓存 |
| `jobs` | 类型、状态、进度、错误、payload、尝试次数、时间 | 检索/导入/媒体作业 |
| `clips` | 通道/时间窗、实际覆盖、路径、编码、状态、大小 | 派生媒体索引 |
| `imports` | 文档/来源 ID、内容哈希、状态、诊断 | Inspect/commit 审计 |
| `search_presets` | NVR、区域、通道 ID、事件类型、最近使用时间 | 用户可复用的事件筛选条件 |
| `search_results` | 检索作业、Interval | 检索会话到事件的精确来源关系 |
| `nvr_event_audits` | NVR、安全摘要 JSON、观测时间 | 只读事件规则/通知快照 |
| `event_previews` | Interval、作业、状态、相对路径 | 派生 JPEG 预览索引 |
| `event_visual_analyses` | Interval、作业、状态、判定、有界结果 JSON | 针对单个 NVR 事件的可选本地检测/跟踪/规则几何证据 |

## 约束

- `(nvr_id, external_channel_id)` 唯一；
- `(source_id, external_channel_key)` 唯一；
- Interval 的 `(source_id, source_event_id)` 唯一；
- `end_ms > start_ms`，媒体窗口覆盖已解析 Interval；
- 分数/置信度为空或位于声明范围；
- Clip 路径规范化后必须位于配置的 clip 根目录；
- Binding 和摄像头映射可以带有效期，以承受设备更换。

## 原始时间与解析时间

Interval 保留来源时间，并单独保存所应用校正：

```text
raw_start_ms/raw_end_ms
clock_correction_ms
resolved_start_ms/resolved_end_ms
```

这样后续修改时钟策略仍可审计。禁止覆盖导入的原始时间戳。

## 录像定位符

`recording_spans.locator` 是适配器私有 JSON，可能过期。浏览器 API 不接收凭据或原始 locator。出片时重新刷新录像覆盖，而不是相信书签中缓存的旧 URI。

## 保留策略

- Interval 和映射是持久元数据；
- 录像 Span 是可刷新缓存；
- Clip 是受配额管理的派生产物；
- 预览 JPEG 也是派生产物，位于同一受校验根目录，并随对应 NVR 来源记录删除；
- 视觉分析行属于派生证据，只保留模型身份和有界摘要，不保存帧、凭据或回放定位符，并随来源 Interval 级联删除；
- 原始轨迹点只作有界诊断，默认不无限保存；
- 删除 clip 同时删除索引和已确认位于根目录内的文件；删除 Interval 不影响 NVR 媒体。
