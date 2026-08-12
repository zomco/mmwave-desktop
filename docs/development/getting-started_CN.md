# 开发者上手

[English](getting-started.md)

## 当前状态

仓库目前契约优先，可执行产品模块尚未落地，但首次检出仍应通过仓库校验。

## 前置要求

- Git 2.40+；
- Python 3.12+，用于仓库检查和建议的控制面；
- 只有 `desktop/package.json` 出现后才需要 Node.js LTS；
- Windows 11 或受支持 Windows 10 环境，用于产品冒烟测试；
- 硬件工作需专用测试 NVR，禁止将生产凭据写入 fixture。

## 首次检出

```powershell
git clone https://github.com/zomco/tracecue.git
Set-Location tracecue
python scripts/ci/verify_repo.py
```

然后按顺序阅读：

1. 根 README 和 `AGENTS_CN.md`；
2. 产品简述和架构总览；
3. 将修改模块的 README；
4. 相关规范和 ADR。

## 选择工作

从路线图下一个未完成退出条件开始。优先交付“探测一台 NVR 并保存能力报告”这类纵向结果，而不是先堆通用框架层。

硬件工作同一改动内新增脱敏 fixture 和兼容记录。契约工作同一改动内更新中英文文档、JSON schema、示例和测试。

## 本地配置

运行时开发配置可以使用未跟踪 `.env` 或用户数据目录；生产凭据必须使用 Windows 保护存储。`.env.example` 中不得出现真实地址或凭据。

## 提交评审前

- 在不破坏无关改动的情况下同步当前 `main`；
- 运行仓库和模块测试；
- 检查 `git diff` 中是否有秘密或误加二进制媒体；
- 架构上下文改变时更新交接记录；
- 说明实际测试和未测试的硬件/固件。
