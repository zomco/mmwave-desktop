# TraceCue

[English](README.md)

面向公寓和小物业的本地优先录像检索。它连接现有 NVR，把事件时间段变成可审阅的书签，并定位或导出对应录像。它不另建一套全量视频库。

| 部分 | 做什么 | 怎么跑 |
| --- | --- | --- |
| `desktop` | 本地 Web 界面、NVR 设置、书签审阅、回放、MP4 导出 | 需要时启动的 Windows 应用 |
| `gateway` | 持续采集雷达或传感器，并保存高置信时间段 | 常开，仅传感器部署需要 |
| `engine` | 与厂商无关的时间段、质量门、`timeline.v1` | 库，不是独立产品 |

NVR 仍是录像存储。只用 NVR 事件时，TraceCue 改善的是整理和导出，**不承诺**误报少于 NVR 自己的智能回放。这个差别来自 2D 雷达轨迹。运行时不依赖 Home Assistant、Docker 或毫米波实验室仓库。唯一允许的雷达运行时依赖是 `mmwave-engine` 包。

本仓库有可执行的 `0.1.0` 开发基线。还没有 NVR 型号或雷达型号获得商业认证。见[实现状态](docs/development/implementation-status_CN.md)。

## 快速使用

开发者检出和测试见[开发入门](docs/development/getting-started_CN.md)。之后：

```powershell
python scripts/ci/verify_repo.py
```

目前没有可以交给住户安装的安装包。二进制发布仍需要第三方声明、签名材料和硬件证据。

## 文档地图

| 想了解 | 看 |
| --- | --- |
| 全部文档 | [文档导航](docs/README_CN.md) |
| 产品目标和不做的事 | [产品简述](docs/product/product-brief_CN.md) |
| 系统形态 | [架构总览](docs/architecture/overview_CN.md) |
| 开发环境 | [开发入门](docs/development/getting-started_CN.md) |
| 已经实现了什么 | [实现状态](docs/development/implementation-status_CN.md) |
| 时间轴交换格式 | [timeline.v1](docs/specifications/timeline-v1_CN.md) |
| HTTP API | [HTTP API v1](docs/specifications/http-api-v1_CN.md) |
| 为什么雷达标签高于 NVR 标签 | [ADR-0009](docs/architecture/decisions/0009-radar-tag-outranks-nvr_CN.md) |
| 桌面 / 网关 / 冷归档引擎 | [desktop](desktop/README_CN.md)、[gateway](gateway/README_CN.md)、[engine](engine/README_CN.md) |
| AI 协作规则 | [AGENTS_CN.md](AGENTS_CN.md) |

## 雷达型号

TraceCue 的高置信时间轴来自 [mmwave-engine](https://github.com/zomco/mmwave-engine)，不是本仓库 `engine/` 里的库。

**1D 雷达不能使用 mmwave-fusion**，也不能提供用来标记录像的位置轨迹。**2D 雷达可以使用全部功能**，包括融合和这个标签。R60ABD1 同时上报高度，列在 2D 里是因为它可以参与融合。

数字和进度与 [mmwave-component](https://github.com/zomco/mmwave-component/blob/main/README_CN.md) 一致。`—` 表示说明书没有给出。标了「精度」的不是距离门宽度。LD2410 在 0.20 m 分辨率下最远 1.6 m。LD2451 按整米上报。LD2450、LD2454 的距离分辨率在每帧目标里。LD2454 性能表写 8 m，安装章节写跟踪 6 m。

### 1D 雷达

| 型号 | 检测距离 | 距离分辨率 | 开发进度 |
| --- | --- | --- | --- |
| LD2410 | 6 m | 0.75 m / 0.20 m | 开发中 |
| LD2410B | 6 m | 0.75 m（协议亦可设 0.20 m） | 测试中 |
| LD2410C | 6 m | 0.75 m（协议亦可设 0.20 m） | 测试中 |
| LD2411 | 2 m（手势 1 m） | — | 开发中 |
| LD2411S | 6 m（微动 3.5 m） | ±5 cm / ±5%（精度） | 开发中 |
| LD2412 | 9 m | 0.75 m | 开发中 |
| LD2420 | 8 m（微动 6 m） | 0.70 m | 开发中 |
| LD2450A | 2 m | 0.2 m（感知精度） | 开发中 |
| LD6002 | 1.5 m（呼吸心率） | — | 开发中 |
| RD-03E | 6 m（微动 3.5 m） | ±5 cm / ±5%（精度） | 开发中 |

### 2D 雷达

| 型号 | 检测距离 | 角度范围 | 距离分辨率 | 开发进度 |
| --- | --- | --- | --- | --- |
| LD2450 | 6 m | 方位 ±60°，俯仰 ±35° | 随帧上报 | 开发中 |
| LD2451 | 100 m | 水平 ±15°，垂直 ±7° | 1 m | 测试中 |
| LD2452 | 6 m | 方位 ±60°，俯仰 ±30° | 0.72 m | 测试中 |
| LD2453 | 6 m | 方位 ±40°，俯仰 ±30° | 0.72 m | 开发中 |
| LD2454 | 8 m | 方位 ±60°，俯仰 ±30° | 随帧上报 | 测试中 |
| R60ABD1 | 2.5 m（呼吸心率 1.5 m） | ±20° | — | 已完成 |

## 许可证

TraceCue 代码使用 [MIT](LICENSE)。随包第三方程序保留各自许可证。见 [ADR-0004](docs/architecture/decisions/0004-licensing-before-contributions_CN.md)。
