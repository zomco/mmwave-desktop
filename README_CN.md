# TraceCue

[English](README.md)

TraceCue 是面向公寓运营和小物业的本地优先录像检索产品。它连接现有 NVR，把事件时间段变成可审阅的书签，并定位或导出对应录像，而不是再建设一套全量视频库。

产品内部划分为三个部分，但前期保持一个仓库、一个产品体系：

| 部分 | 职责 | 运行形态 |
| --- | --- | --- |
| `desktop` | 本地 Web 界面、NVR 管理、书签审阅、回放和 MP4 导出 | 按需启动的 Windows 应用 |
| `gateway` | 持续采集雷达/传感器数据，并持久化高置信时间段 | 传感器版本中的常驻伴侣 |
| `engine` | 厂商无关 Interval 模型、质量门控、合并/过滤规则和 `timeline.v1` | 嵌入式库，不是独立终端产品 |

## 产品边界

NVR 始终是权威录像存储。TraceCue 只索引元数据书签，并按需解析媒体；不会持续拉取、转码和保存全部 NVR 录像。

首个交付切片使用海康 ISAPI 和 RTSP。仅使用 NVR 原生事件时，TraceCue 改善的是整理和出片流程，**不承诺**在误报率上显著优于海康原生智能回放。真正差异化来自后续毫米波轨迹等高置信时间轴。

TraceCue 运行时不依赖 `mmwave-component`、`mmwave-card`、`mmwave-fusion`、Home Assistant 或 Docker。这些仓库继续作为实验室和技术参考，而不是产品依赖。

## 仓库状态

仓库当前已经固化产品、架构和交付契约，供实现阶段开始使用；可执行产品代码尚未落地。请查看[路线图](docs/product/roadmap_CN.md)和[文档导航](docs/README_CN.md)。

## 从这里开始

- 产品目标和约束：[产品简述](docs/product/product-brief_CN.md)
- 系统形态和边界：[架构总览](docs/architecture/overview_CN.md)
- 开发者上手：[开发入门](docs/development/getting-started_CN.md)
- AI 协作说明：[AGENTS_CN.md](AGENTS_CN.md)
- 时间轴交换格式：[timeline.v1 规范](docs/specifications/timeline-v1_CN.md)
- CI/CD 与发布门禁：[CI/CD](docs/operations/ci-cd_CN.md)

## 许可证提示

仓库创建时选择了 GPL-3.0，但拟议中的商业/开源边界尚未与该许可证选择完成协调。在 [ADR-0004](docs/architecture/decisions/0004-licensing-before-contributions_CN.md) 解决前，不要接受外部代码贡献，也不要向产品模块复制第三方代码。
