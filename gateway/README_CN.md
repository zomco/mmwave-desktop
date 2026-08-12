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

- NVR 凭据、录像检索或 FFmpeg 媒体导出；
- Desktop UI/业务工作流；
- 将 Home Assistant 作为必需运行时。

## 产品化规则

实验室仓库提供协议、校准和质量知识。产品 Gateway 必须独立构建，并只承诺经过认证的硬件子集。“Lab 已支持”不等于商业硬件已认证。

## 首个可执行切片

一种认证 2D 雷达/型号无人值守运行，维护时钟健康，产生确定性 `presence.traverse` Interval，并在 Desktop 离线时仍保存记录。
