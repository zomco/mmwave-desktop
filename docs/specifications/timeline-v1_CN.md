# timeline.v1 规范

[English](timeline-v1.md)

`timeline.v1` 是批量交换时间 Interval 的文档，不是实时传感器协议、视频容器或 fusion 数据库导出。机器可读契约位于 [`contracts/timeline/v1/schema.json`](../../contracts/timeline/v1/schema.json)。

## 文档字段

| 字段 | 必填 | 规则 |
| --- | --- | --- |
| `schema_version` | 是 | 固定 `timeline.v1` |
| `document_id` | 是 | 导出/文档唯一标识 |
| `source_id` | 是 | 稳定的生产者/站点标识；不得是密钥 |
| `generated_at` | 是 | 带时区 RFC 3339 |
| `producer` | 是 | 生产软件名称和版本 |
| `coverage` | 是 | 文档表示的时间范围和完整性 |
| `channels` | 是 | 来源内部通道声明 |
| `intervals` | 是 | 零个或多个 Interval |

`coverage.completeness` 取值 `complete`、`partial` 或 `unknown`。完整文档不代表后续导入中缺失的旧记录应该被删除。

## Channel

`channels[].id` 在 `source_id` 下稳定唯一。`kind` 表示宽泛来源类型，例如 `mmwave`、`door_contact`、`nvr_event` 或 `other`。`external_refs` 保留上游标识，但不把它们当作主键。

## Interval

| 字段 | 必填 | 规则 |
| --- | --- | --- |
| `id` | 是 | 在 `source_id` 下稳定；导入幂等键 |
| `channel_id` | 是 | 引用已声明通道 |
| `event_type` | 是 | 开放点分命名空间，如 `presence.traverse` |
| `start_at`、`end_at` | 是 | 带明确时区，且 `end_at > start_at` |
| `quality` | 否 | 数据/轨迹质量评估 |
| `confidence` | 否 | 0～1 的事件分类置信度 |
| `media_window` | 否 | 覆盖事件的建议媒体时间窗 |
| `tags` | 否 | 可移植低基数标签 |
| `source_ref` | 否 | 上游事件标识 |
| `attributes` | 否 | 按生产者命名空间扩展 |

质量和置信度必须分开。质量回答观测与轨迹是否可用；置信度回答生产者有多相信该分类事件发生。

可移植 `quality.score` 范围为 0～1。使用其他原生量程的生产者必须归一化，例如当前 Lab fusion 的 0～100 分需要除以 100；原始分数可以保存在带命名空间的 `attributes` 中。

`quality.gate` 取值 `pass`、`fail` 或 `unknown`。失败 Interval 可以保留用于诊断，但默认不进入高置信视图。

## 事件类型建议

命名空间开放。初始建议：

- `presence.traverse`
- `presence.arrival`
- `presence.departure`
- `presence.dwell`
- `zone.enter`
- `zone.exit`

消费者必须保留未知类型；可以隐藏不支持的行为，但不应因此拒绝整个文档。

## 导入语义

- 按 `(source_id, interval.id)` 幂等 upsert；
- 拒绝不带明确时区的时间；
- 拒绝同一文档中重复通道或 Interval ID；
- 缺少旧 Interval 不代表删除；
- 未映射通道可进入待映射状态，但不能出片；
- 保留原始文档/来源引用用于审计；
- 时钟校正在不可变来源 Interval 之外解析，禁止静默重写原始时间。

## 来源通道到媒体的映射

来源通道先映射业务空间，再由空间映射一个或多个 NVR 通道：

```text
radar-hall-east → 东侧走廊 → 摄像头 3（主）、摄像头 7（辅）
```

这种模型可以承受摄像头更换并支持多个视角。禁止将 timeline 通道直接持久映射到海康 `trackID`。
