# TraceCue Desktop

[English](README.md)

Desktop 是主要用户应用：一个在回环地址同源提供 SPA 与 HTTP API 的 Windows 进程。

## 负责

- NVR 添加、能力证据和通道别名；
- 书签检索和 timeline 导入/映射；
- 通过适配器解析录像覆盖；
- 持久后台作业和 FFmpeg 出片；
- SQLite 迁移、本地 clip 配额和支持诊断。

## 不负责

- 应用关闭时持续采集传感器；
- 雷达协议/融合算法；
- 第二套全量录像库；
- MVP 中的云端或 LAN 远程访问。

## 初始实现建议

控制面使用 Python 3.12/FastAPI，SPA 使用 React/TypeScript/Vite，配合 SQLite、FFmpeg/FFprobe 子进程和 one-folder Windows 包。该组合在实现 ADR 接受前仍是建议。

## 契约依赖

Desktop 可以依赖 `engine` 和 `integrations/hikvision`。它消费 `timeline.v1`，不得直接读取 gateway 存储。公共路由遵循 HTTP API v1 草案。

## 首个可执行切片

对一个受支持 NVR、一个通道和一个时间窗，生成可在浏览器播放的 H.264 MP4，并明确报告认证、时钟和录像缺口。
