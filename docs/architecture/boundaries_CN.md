# 产品与仓库边界

[English](boundaries.md)

## 一个产品，三个模块

用户购买或安装的是 TraceCue，而不是三个无关产品。内部模块使用独立接口，使 gateway 和 engine 将来可以独立发版，而无需重写 desktop。

## 与毫米波实验室的关系

| 实验室仓库 | 产品复用的知识 | 禁止耦合 |
| --- | --- | --- |
| `mmwave-component` | 协议知识、设备坐标变换、边界过滤、fixture | ESPHome/HA 运行时依赖 |
| `mmwave-card` | 校准 UX、房间/区域编辑器、坐标约定 | Lovelace/HA 实体运行时依赖 |
| `mmwave-fusion` | 跟踪、轨迹质量、`traverse` 判断、金样导出 | import HA 集成，或把其数据库 schema 当作产品 API |

TraceCue 可以在注明来源并完成许可证检查后迁移算法、读取导出的 `timeline.v1`，并用 Lab 做金样验证。不得添加产品构建/运行所必需的子模块或 import。

## 开源边界

此前建议的边界是 `engine` 可能开源、产品整合闭源。但当前仓库实际使用 GPL-3.0。在 ADR-0004 解决前，以仓库现有许可证为准，并暂停外部代码贡献。

## 部署边界

- 仅 NVR：desktop 可按需启动，不需要 gateway；
- 历史传感器时间轴：必须有常驻生产者，可以是 gateway 或未来具备能力的固件；
- 多雷达融合预计需要 gateway 级算力；
- 云中继、远程访问和局域网开放属于未来独立威胁模型。

## 明确否决或延后的方向

- 微信小程序作为直连 NVR 的主路径；
- HTTPS 云端 JavaScript 直连私网 NVR；
- 把 Home Assistant 作为大陆市场前提；
- 建设第二套常驻全量录像/转码库；
- 创始人负责全国多雷达上门安装；
- 永久只靠同源 NVR 智能事件做差异化；
- 在 Python 中解码/渲染视频。

若需修改其中任何一项，必须用 ADR 记录新证据、冲突和迁移代价。
