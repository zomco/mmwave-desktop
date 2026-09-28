# ADR-0009：雷达标签权重大于 NVR 标签

[English](0009-radar-tag-outranks-nvr.md)

- 状态：已接受
- 日期：2026-09-28
- 相关：[ADR-0008](0008-local-clip-review_CN.md)

## 背景

TraceCue 和 mmwave-fusion 都用毫米波轨迹给安防视频打标签，方便事后回查。有些 NVR 自己已有区域入侵、越界侦测等标签。这些标签有大量灯光、影子和天气误报，清洗之后才有用，而且它们不是雷达观测。

`mmwave-engine` 是共用的跟踪核心。`tracecue-engine` 是本仓库的时间线库。协作者不得把二者合并，也不得把未清洗的 NVR 标签当成训练真值。

## 决策

1. `mmwave-engine` 是权重最高的视频标签。它的 `enter`、`dwell`、`traverse` 决定打开哪段抓拍或短片。NVR 标签不得进入 `FusionEngine.step()`。
2. 以后的对照步骤可以按同一区域、重叠时间窗给雷达事件排序。排序不改写雷达事件。`radar_only` 仍然显示。`nvr_only` 是低权重提示，不是已确认的人。时间对上但区域对不上时留给人看。
3. 原始 NVR 标签不是训练集，必须先清洗。唯一的调参标签是人工复核结论：`person`、`pet`、`false_positive`、`uncertain`。先不要训练模型。用清洗后的标签调整确定性阈值。
4. `tracecue-engine` 留在本仓库。它负责冷存档的 `timeline.v1`，以及把雷达事件、清洗后的 NVR 时间段和人工结论对齐的离线参考导出。`mmwave-engine` 不得导入它。mmwave-fusion 不得依赖它。
5. 区域编号对照留在外壳：桌面的通道绑定，或融合的摄像机配置。引擎只收到已经对照过的 `zone_id`。

## 后果

删掉 `tracecue-engine` 会破坏时间线导入。把海康 XML 送进 `mmwave-engine` 会把跟踪器绑到一家摄像机厂商。用未清洗的 NVR 标签当教师，会把 NVR 的误报抄进雷达评分。
