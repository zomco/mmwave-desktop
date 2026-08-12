# 开发者上手

[English](getting-started.md)

## 当前状态

仓库现已包含可执行的 0.1.0 开发基线。软件契约和合成 fixture 可在无硬件环境测试；兼容性、编解码和安装器声明仍需要经授权硬件与发布证据。

## 前置要求

- Git 2.40+；
- Python 3.12+，用于仓库检查和建议的控制面；
- Node.js LTS，用于 Desktop SPA；
- Windows 11 或受支持 Windows 10 环境，用于产品冒烟测试；
- 硬件工作需专用测试 NVR，禁止将生产凭据写入 fixture。
- 真实媒体测试需要固定的 FFmpeg/FFprobe 输入；运行 `./packaging/windows/fetch-ffmpeg.ps1`。二进制保持忽略，绝不提交。

## 首次检出

```powershell
git clone https://github.com/zomco/tracecue.git
Set-Location tracecue
python scripts/ci/verify_repo.py
python -m pip install -r requirements-dev.lock.txt
python -m pip install --no-build-isolation --no-deps -e ./engine -e ./integrations/hikvision -e ./gateway -e ./desktop/backend
python -m pytest engine/tests integrations/hikvision/tests gateway/tests desktop/backend/tests
npm ci --prefix desktop/frontend
npm test --prefix desktop/frontend
npm run build --prefix desktop/frontend
```

如需在本地连接硬件并测试媒体导出，请先取得固定工具，再从仓库启动可编辑安装的桌面服务：

```powershell
.\packaging\windows\fetch-ffmpeg.ps1
$env:TRACECUE_FRONTEND_DIR = (Resolve-Path .\desktop\frontend\dist).Path
tracecue-desktop
```

Windows 下，可编辑检出会自动发现 `packaging/windows/tools/` 中已经校验的二进制。
若开发目录布局不同，可通过 `TRACECUE_FFMPEG_PATH` 和
`TRACECUE_FFPROBE_PATH` 指定可执行文件的完整路径；打包版本仍使用程序相邻的
`tools/` 目录。

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
