# 工作区开发入口

本仓库的 AI 开发、测试和维护规范统一在 [mmwave-workspace](https://github.com/zomco/mmwave-workspace/blob/main/docs/development/repositories/mmwave-desktop_CN.md) 管理。

在工作区开发时，先读根目录 AGENTS.md、`docs/development/repositories/mmwave-desktop_CN.md` 和 `docs/development/README.md`。Skill 位于根目录 `.agents/skills/`，命令入口是 `python scripts/dev.py list`。本文件仅作路由，不新增本地规则或复制 Skill。独立检出时使用产品 README/CI；需要内部维护流程时须检出工作区，不猜测其内容。
