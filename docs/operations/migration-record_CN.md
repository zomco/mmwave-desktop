# 项目资料迁移记录

[English](migration-record.md)

- 迁移日期：2026-08-12
- 目标：`D:\Users\zomco\Documents\GitHub\tracecue`
- 来源上下文：在 `mmwave-workspace` 及三个 Lab 子模块旁形成的产品/架构决策。

## 已迁移内容

- TraceCue/Clipmark 产品问题、目标客户、价值和非目标；
- Desktop/Gateway/Engine 产品和部署边界；
- NVR 权威媒体架构及 FFmpeg 策略；
- 海康能力风险和兼容证据模型；
- HTTP API、SQLite/领域模型和 `timeline.v1` 草案；
- Windows 打包、CI/CD、安全、验证和 UX 指导；
- AI 协作规则、交接格式和开发者贡献指南；
- 商业/开源/渠道假设和命名状态。

## 未迁移内容

此前 `mmwave-workspace` 中没有 TraceCue 源代码。没有复制 `mmwave-*` 源码、Git 历史、运行时子模块或 Home Assistant 依赖。这些仓库继续作为 Lab，并通过明确契约产生 fixture/导出。

## 事实来源变化

从本次迁移开始，TraceCue 产品决策归本仓库文档/ADR 管理。`mmwave-workspace` 只继续作为跨仓 Lab 测试和研究的事实来源。聊天历史不是持久事实来源。

## 后续

ADR-0004 已于 2026-08-12 接受，单仓现使用 MIT。若后续历史资料与已接受 ADR 冲突，应新增取代 ADR，而不是静默混合假设。

## 0.1.0 实现迁移

可执行代码现会在首次启动时初始化 Desktop SQLite schema version 1。新数据库创建文档约定的 NVR、能力、通道、来源、空间/绑定、Interval、录像段、作业、片段和导入表。此前没有可执行数据库需要迁移。重启时，未完成的 `running` 作业会改为 `interrupted`；系统不会猜测媒体工作已经完成。

Gateway 为常驻 Interval 和有界诊断维护独立内部 SQLite。Desktop 永不读取该数据库；数据通过 `timeline.v1` 跨越边界。

### Desktop schema v2-v4

Schema v2 新增历史筛选/检索结果、只读 NVR 事件审计证据、事件 JPEG 预览和 Clip 来源。Schema v3 新增实测 NVR UTC 偏移、历史筛选的多 NVR 摄像机范围、会过期的通道截图和缓存事件 WebP 动图。已有筛选继续使用原摄像机列表，已有 Interval/Clip 的 UTC 时间戳不改变；已有 NVR 行在重新探测写入显式偏移前，会回退解析已保存的 POSIX 时区。由于回放参数映射发生变化，schema v4 会使旧 JPEG 预览缓存失效；后续按需重新生成，不会改动 NVR 原始录像。
