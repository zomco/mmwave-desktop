# 产品简述

[English](product-brief.md)

## 问题

公寓和小物业运营人员经常需要拖动监控录像寻找某次来访或经过。现有海康 NVR 已有事件/智能回放，但楼道灯、反光和目标区域之外的活动造成大量误报，时间轴经常被涂满。问题是信噪比差，而不是没有事件列表。

## 产品定义

TraceCue 是本地回查应用。`mmwave-engine` 用二维雷达轨迹给一次经过打标签，并打开直播流上的抓拍和短片。NVR 自带的区域入侵、越界侦测是以后的低权重提示。它们有大量误报，清洗之后才能给雷达事件排序，或进入离线参考集。NVR 时间轴检索仍是可选冷存档（[ADR-0008](../architecture/decisions/0008-local-clip-review_CN.md)、[ADR-0009](../architecture/decisions/0009-radar-tag-outranks-nvr_CN.md)）。

```text
mmwave-engine 标签（权重最高）
        +
可选的已清洗 NVR 标签
        ↓
抓拍 / 直播短片
        ↓
只有短片缺失时才查 NVR 时间轴
```

## 目标客户

- 公寓运营、二房东和小物业团队；
- 已经会打开海康客户端翻录像；
- 不想使用 Docker、Home Assistant、编译固件或第二套 VMS；
- 付费者是运营方/业主，后期可经本地监控安装商交付。

## 分阶段能力

| 阶段 | 能力 | 诚实价值承诺 |
| --- | --- | --- |
| NVR 基础 | 读取受支持的海康录像/事件元数据、通道别名、筛选、回放/导出 | 更快整理和出片；不承诺降误报 |
| Timeline | 导入/读取 `timeline.v1`，将来源通道映射至空间/NVR 通道 | 在满足实测召回率前提下减少书签 |
| 产品化感知 | 无 HA 的常驻 gateway/雷达伴侣 | 形成端到端高置信时间轴产品 |
| 扩展 | 更多来源、可选 LAN、渠道分发、ONVIF 品牌 | 扩大部署范围和持续服务 |

## 成功标准

1. 新 Windows 用户按照文档，在一小时内从受支持海康 NVR 看到事件时间轴。
2. 对受支持 H.264 测试用例，点击事件后 P95 目标为 30 秒内开始播放或得到可播 MP4。
3. 不要求 Docker、Home Assistant 或云页面直连私网 NVR。
4. NVR 冷存档路径不依赖 `mmwave-*`。雷达回查可以依赖已发布的 `mmwave-engine` 包，且不得把 `mmwave-fusion` 或 `tracecue-engine` 导入该包。
5. 在人工标注金样中，高置信书签在达到约定重要事件召回率的同时减少审阅量。

## 非目标

- 替代 NVR 录像系统；
- 持续转码所有通道；
- 声称同一份海康事件数据能神奇消除海康误报；
- 把微信小程序作为主客户端；
- 由创始人建立全国上门安装团队；
- 要求客户使用 Home Assistant。

## 商业形态

TraceCue 是一个产品体系。`desktop` 是回查应用，`gateway` 是常驻生产者。`mmwave-engine` 是共用的雷达标签。本仓库的 `tracecue-engine` 是冷存档时间线和离线参考导出，不是 `mmwave-engine` 的运行时助手（[ADR-0009](../architecture/decisions/0009-radar-tag-outranks-nvr_CN.md)）。
