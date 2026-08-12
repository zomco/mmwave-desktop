# TraceCue Engine

[English](README.md)

Engine 是 Desktop 导入路径和 Gateway 生产者共用的厂商无关 Interval 核心。它是库与契约实现，不是面向用户的独立进程。

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
