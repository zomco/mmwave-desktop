# Windows 与 FFmpeg 打包

[English](windows-packaging.md)

## 打包形态

首版优先按用户安装的 one-folder 包。相比 one-file，它启动更快，不会每次解压 FFmpeg/Python，也更容易排查。

建议路径：

```text
程序：%LocalAppData%\Programs\TraceCue
数据：%LocalAppData%\TraceCue
片段：%USERPROFILE%\Videos\TraceCue
```

安装器默认不要求管理员权限、不启用开机启动、不开放防火墙端口，也不删除用户数据。ADR-0006 的临时片段分享只由用户在运行时显式调用；Windows 可在此时请求专用网络权限，但安装器不会预先授权端口。卸载时提供独立明确的数据删除选项。

## 进程行为

- 单实例锁；
- 托盘操作：打开、状态、退出；
- 稳定首选端口和安全备用端口；
- 默认监听回环地址；
- 优雅取消作业并恢复中断状态；
- 支持包在导出前提供脱敏预览。

## 代码签名

主程序、安装器、卸载器和未来更新器使用一致可信身份签名。证书材料只保存于受保护 CI Secret/HSM 服务。早期签名版本仍可能触发 SmartScreen；签名证明发布者身份，但不保证立即获得信誉。

## FFmpeg 分发

- 固定版本、不可变发布 URL、源码提交和 SHA-256；
- 发布来源记录 `ffmpeg -version` 和 `-buildconf`；
- 优先使用可验证 LGPL 构建，并随包提供所需许可证/源码获取声明；
- 禁止 `nonfree`；GPL 构建需结合最终产品许可证重新评估；
- `ffprobe` 与 `ffmpeg` 一同分发；
- 编解码专利问题与 LGPL/GPL 合规分开评估。

### 0.1.0 固定输入

TraceCue 固定使用 BtbN 按月保留的 Windows x64 静态 LGPL 构建 `n8.1.2-34-g9b6c8969e0-20260731`，发布标签为 `autobuild-2026-07-31-14-10`。FFmpeg 下载页将 BtbN 列为 Windows 二进制提供方。归档、可执行文件、FFmpeg 源码提交 `9b6c8969e05b4f0b29f0f85cd501be6b3e582e6b`、BtbN 构建脚本提交 `a99e8230eae00d1cee38f23076a7a1f55cd984e2`、许可证文本及全部 SHA-256 均记录在 `release/manifest.json`。

该构建启用 `--enable-version3` 和 `--enable-libopenh264`，不启用 `--enable-gpl`、`--enable-nonfree`，并禁用 `libx264`、`libx265`。因此 TraceCue 的兼容转码回退使用 `libopenh264`。编解码专利审查仍是独立产品发布决策。

在不提交二进制的前提下获取并验证打包输入：

```powershell
./packaging/windows/fetch-ffmpeg.ps1 -IncludeSourceSnapshots
```

脚本验证归档及逐个可执行文件哈希、版本/构建配置、所需 LGPL/GPL 文本和可选源码快照。二进制写入已忽略的 `packaging/windows/tools/`，源码快照写入已忽略的 `release/output/source/`。

## 媒体策略

- RTSP 默认 TCP；
- 固定可执行路径和参数数组，禁止 shell 拼接；
- 设置连接、无数据和总作业超时；
- 初期每台 NVR 同时只运行一个媒体作业；
- H.264 优先直接封装，H.265/视频及不兼容音频使用明确兼容配置；
- MP4 使用 `faststart`，先写 `.partial` 再原子完成；
- 检查空间、限制 clip 配额，并报告部分录像覆盖。

## 发布内容

每个二进制版本包含应用版本、数据库迁移版本、FFmpeg 来源、第三方声明、受支持兼容矩阵、校验和文件及签名产物元数据。

## 已实现自动化与当前门禁

- `packaging/windows/build.ps1 -Mode Verify` 运行仓库/安全、Python 模块和前端检查。
- `-Mode Release` 构建 PyInstaller one-folder 应用、签名、生成按用户安装的 Inno Setup 安装器、CycloneDX SBOM 和校验和；缺少显式输入时拒绝继续。
- `packaging/windows/smoke.ps1` 隐藏启动打包进程，验证回环状态和 SQLite 初始化，然后删除隔离临时数据。
- ADR-0004 与 FFmpeg 选择已经解决。`release/manifest.json` 在所有静态合入依赖的完整对应源码/声明完成镜像和审查、签名凭据获批、签名安装包/硬件测试通过前继续保持 `release_ready=false`。
