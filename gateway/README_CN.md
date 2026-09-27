# TraceCue Gateway

[English](README.md)

Gateway 是传感器版本中的常驻时间轴生产者。初期它是 TraceCue 产品的配套组件，而不是单独营销的应用。

## 负责

- 持续设备采集和重连策略；
- 适配器/型号身份和来源时钟健康；
- 有界原始诊断和可选短期轨迹缓冲；
- 调用 Engine、质量判断和持久 Interval 交付；
- 使用版本化 timeline 契约进行本地导出/同步。

## 不负责

- NVR 凭据或 NVR 时间轴检索。直播抓拍使用 FFmpeg 参数数组，不经过 shell。
- Desktop UI/业务工作流；
- 将 Home Assistant 作为必需运行时。

## 产品化规则

实验室仓库提供协议、校准和质量知识。产品 Gateway 必须独立构建，并只承诺经过认证的硬件子集。“Lab 已支持”不等于商业硬件已认证。

## 首个可执行切片

一种认证 2D 雷达/型号无人值守运行，维护时钟健康，产生确定性 `presence.traverse` Interval，并在 Desktop 离线时仍保存记录。

## 已实现基线

`tracecue-gateway` 0.1.0 已实现有界的实验性 JSON-line TCP 采集面、重连退避、滚动来源时钟健康、有界短轨迹状态、确定性穿越 Interval、质量门、有界诊断、SQLite 持久化和 `timeline.v1` 导出。fixture 测试证明 Desktop 离线时 Interval 仍会保留。

```powershell
python -m pip install -e ./engine -e "./gateway[dev]"
python -m pytest gateway/tests
```

尚无任何实体雷达/型号通过认证。JSON-line 适配器明确属于实验性能力。融合回查环（`fusion_review.py`）接收 v1 目标帧并调用 `mmwave-engine`。只有有人/无人的传感器不进入融合轨迹。见[常驻服务](../docs/operations/resident_CN.md)。
