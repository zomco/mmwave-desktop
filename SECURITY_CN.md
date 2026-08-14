# 安全策略

[English](SECURITY.md)

## 报告方式

不要在公开 issue 中披露漏洞。GitHub 私密漏洞报告启用后请优先使用；否则通过仓库所有者 GitHub 主页列出的私密联系方式报告。请包含受影响版本、复现步骤、影响和已知缓解方案。

## 安全边界

- TraceCue 默认只监听回环地址。
- 一般局域网 API 开放不属于 MVP；实现时必须同时加入鉴权、CSRF 防护、Origin 检查，以及明确的防火墙/安装流程。ADR-0006 的窄范围例外是用户显式开启、仅限一个已生成片段的 256 位只读能力链接：令牌只存内存、15 分钟过期、仅接受 GET/HEAD、不记录令牌日志，也不暴露 API 或 NVR 数据。
- NVR 凭据保存在 Windows Credential Manager 或 DPAPI 保护的存储中，禁止明文写入 SQLite。
- 日志和支持包必须脱敏认证头、密码、客户隐私数据及带凭据 URL。
- 导入的 timeline 文档和 NVR XML/JSON 都是不可信输入。
- FFmpeg 等子进程使用固定可执行文件和参数数组，禁止 shell 展开。
- clip 下载必须校验资源归属、路径和 HTTP Range 边界。

## 支持版本

目前没有生产版本。首个 beta 标签发布后开始版本化安全支持；在此之前，请针对 `main` 报告问题。
