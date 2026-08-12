# 依赖评估

[English](dependency-assessment.md)

直接依赖刻意保持精简。精确开发版本位于 `requirements-dev.lock.txt` 和 `desktop/frontend/package-lock.json`；仅打包版本位于 `packaging/windows/requirements.lock.txt`。

| 依赖 | 原因 | 许可证检查 | 所有者维护评估 |
| --- | --- | --- | --- |
| FastAPI / Starlette / Pydantic | 类型化同源 HTTP API 和校验 | MIT / BSD-3-Clause / MIT | 广泛使用、上游活跃；框架代码隔离在 Desktop，使 Engine/Gateway 保持独立 |
| Uvicorn | 回环 ASGI 服务 | BSD-3-Clause | 成熟且可在 ASGI 后替换；不启用 LAN 暴露 |
| React / React DOM | Desktop SPA 状态与可访问组件 | MIT | 上游成熟；仅同源浏览器 UI 依赖它 |
| Vite / TypeScript | 确定性前端构建与静态检查 | MIT / Apache-2.0 | 上游活跃；仅构建期使用，保留精确 lock |
| Vitest | 前端不变量测试 | MIT | 仅构建/测试；若上游维护变化，小型测试可迁移 |
| pytest / httpx | Python 行为与 HTTP 集成测试 | MIT / BSD-3-Clause | 仅开发；生产代码不 import |
| PyInstaller | Windows one-folder 组装 | GPL-2.0-or-later + bootloader 例外 | 仅打包且固定版本；每次发布复核当时例外与声明 |
| Inno Setup | 按用户 Windows 安装器 | 自定义再分发条款 | 外部构建工具，不 vendoring；发布前所有者必须复核当时商业再分发条款 |
| FFmpeg / FFprobe | 在不使用 Python 视频解码的前提下 remux/转码/探测 NVR 媒体 | 依构建而定的 LGPL/GPL | 不下载或 vendoring；发布门禁要求识别 LGPL 兼容构建、哈希、构建配置和精确声明/源码提供姿态 |

海康 HTTP Digest、XML 解析、SQLite 和 Gateway TCP 采集使用 Python 标准库，避免新增协议/运行时依赖。不受信任 XML 若包含 DTD/实体声明会被拒绝，并受深度/大小限制。

Dependabot 覆盖 npm 和全部 Python 模块 manifest；CodeQL 覆盖可执行 Python 与 TypeScript。依赖更新必须同步精确 lock 并重新运行所有模块测试。

