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

接受外部代码前解决 ADR-0004，然后开始 M1。若后续历史资料与已接受 ADR 冲突，应新增取代 ADR，而不是静默混合假设。
