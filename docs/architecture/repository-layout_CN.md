# 目录架构

[English](repository-layout.md)

```text
tracecue/
├─ desktop/                  按需启动的本地 Web 应用
├─ gateway/                  常驻来源采集
├─ engine/                   厂商无关 Interval 核心
├─ integrations/hikvision/  海康适配器边界
├─ contracts/timeline/v1/   机器可读公共契约
├─ docs/                     产品与工程事实来源
├─ scripts/ci/               低依赖仓库检查
└─ .github/                  协作、CI 和发布自动化
```

## 依赖方向

```text
desktop ───────→ engine
gateway ───────→ engine
desktop ───────→ integrations/hikvision

engine ─X→ desktop、gateway、海康、HA 或 FFmpeg
gateway ─X→ desktop UI 或 NVR 媒体
```

跨模块数据必须通过类型化接口或版本化契约传递。模块不得直接读取另一个模块的 SQLite 表。

## 计划中的模块内部结构

可执行语言/框架在首个实现 ADR 前仍是暂定项。目前建议 `desktop/backend/` 使用 Python/FastAPI，`desktop/frontend/` 使用 React/TypeScript，engine 使用低依赖 Python，FFmpeg 作为子进程。这些目录在代码落地时再创建，禁止为抽象而创建空目录。

## 文档归属

- 产品承诺：`docs/product/`；
- 运行时决策：`docs/architecture/` 和 ADR；
- 公共数据/API 契约：`docs/specifications/` 与 `contracts/`；
- 可复现开发/运维流程：`docs/development/` 和 `docs/operations/`；
- AI 会话之间容易丢失的上下文：`AGENTS*` 和 `docs/ai/`。
