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

安装器默认不要求管理员权限、不启用开机启动、不开放防火墙端口，也不删除用户数据。卸载时提供独立明确的数据删除选项。

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

- 固定版本、来源 URL 和 SHA-256；
- 发布来源记录 `ffmpeg -version` 和 `-buildconf`；
- 优先使用可验证 LGPL 构建，并随包提供所需许可证/源码获取声明；
- 禁止 `nonfree`；GPL 构建需结合最终产品许可证重新评估；
- `ffprobe` 与 `ffmpeg` 一同分发；
- 编解码专利问题与 LGPL/GPL 合规分开评估。

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
