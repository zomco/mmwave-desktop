# TraceCue Desktop

[English](README.md)

Desktop 是主要用户应用：一个在回环地址同源提供 SPA 与 HTTP API 的 Windows 进程。

## 负责

- NVR 添加、能力证据和通道别名；
- 事件优先的录像检索、区域/通道/类型筛选保存和 timeline 导入/映射；
- 通过适配器解析录像覆盖；
- 持久后台作业和 FFmpeg 出片；
- SQLite 迁移、本地 clip 配额和支持诊断。

## 不负责

- 应用关闭时持续采集传感器；
- 雷达协议/融合算法；
- 第二套全量录像库；
- MVP 中的云端或 LAN 远程访问。

## 初始实现建议

可执行基线使用 Python 3.12/FastAPI、React/TypeScript/Vite、SQLite、FFmpeg/FFprobe 子进程和 one-folder Windows 包。ADR-0005 在托管 Windows/Linux CI 与打包证据满足全部接受条件前仍保持“待决”。

## 契约依赖

Desktop 可以依赖 `engine` 和 `integrations/hikvision`。它消费 `timeline.v1`，不得直接读取 gateway 存储。公共路由遵循 HTTP API v1 草案。

## 首个可执行切片

对一个受支持 NVR、一个通道和一个时间窗，生成可在浏览器播放的 H.264 MP4，并明确报告认证、时钟和录像缺口。

## 已实现基线

后端已实现 HTTP API v1 路由、SQLite migration v1-v5、DPAPI 凭据引用、有界 ONVIF/私有网段发现、基于证据的 NVR 添加、按摄像机区分普通/Smart 事件且按端点归一化画面覆盖层的规则审计、带开始/停止时长配对的有界历史报警日志检索、缓存的摄像机识别截图（优先低码率码流、回退最近录像）、单摄像机历史筛选、持久 Trace 会话与审阅状态、只返回密度/时长/类型统计的摘要、缓存的 JPEG/WebP 事件预览、持久化作业、时间轴导入/映射、FFmpeg remux/转码/校验、按设备本地时间校正且边界受限并带事件/检索来源的原子片段、配额保留和有界 Range 交付。React/Tailwind SPA 的主功能只保留事件检索、设备中心、候选与导出、设置四项；事件检索要求一个摄像机、时间范围和至少一种事件类型，用户选择二次统计条件后才加载事件画面。连续录像文件只作为媒体来源，不作为事件结果；时间轴对照/映射作为后期高级功能保留。

```powershell
python -m pip install -r requirements-dev.lock.txt
python -m pip install --no-build-isolation --no-deps -e ./engine -e ./integrations/hikvision -e ./desktop/backend
python -m pytest desktop/backend/tests
npm ci --prefix desktop/frontend
npm test --prefix desktop/frontend
npm run build --prefix desktop/frontend
```

真实 NVR 的认证、检索、媒体行为和 FFmpeg 编解码结果仍属于硬件测试，不能作为 CI 已证明能力。
