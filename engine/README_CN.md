# TraceCue Engine

[English](README.md)

Engine（`tracecue-engine`）是 Desktop 导入路径和 Gateway 生产者共用的厂商无关 Interval 库。它不是面向用户的独立进程，也不是雷达跟踪器。权重最高的视频标签是单独的 `mmwave-engine` 包（[ADR-0009](../docs/architecture/decisions/0009-radar-tag-outranks-nvr_CN.md)）。

这个库以后可以导出离线 `timeline.v1` 参考，把雷达事件、清洗后的 NVR 时间段和人工复核结论对齐。原始 NVR 标签不是这份参考。`mmwave-engine` 不得导入本包。

## 负责

- 来源/通道/Interval 值类型；
- 时间和不变量校验；
- 确定性身份及幂等合并基础能力；
- 质量门控结果表达；
- Interval 合并/过滤和 `media_window` 计算；
- `timeline.v1` 读写和 schema 兼容。

## 依赖规则

Engine 不依赖 Desktop、Gateway、海康、FFmpeg、Home Assistant 或操作系统凭据存储。领域逻辑在注入时钟/ID 策略后应保持确定性，并能脱离硬件测试。

## 版本管理

JSON 契约使用 `timeline.v1`。出现外部消费者后，库发布遵循 SemVer。只有 schema/版本策略明确允许时，向后兼容读取器才可接受新增字段。

## 首个可执行切片

校验仓库中的示例，拒绝无时区、时间范围错误和通道引用错误，并证明按 `(source_id, interval.id)` 幂等导入。

## 已实现基线

`tracecue-engine` 0.1.0 已实现不可变时间轴值类型、严格且限制大小的 `timeline.v1` 读写、显式时区时间戳、确定性 ID、质量门结果、媒体窗口、过滤、确定性合并和幂等 upsert 基础能力。它不依赖 Desktop、Gateway、海康、FFmpeg 或 HA。

```powershell
python -m pip install -e "./engine[dev]"
python -m pytest engine/tests
```
