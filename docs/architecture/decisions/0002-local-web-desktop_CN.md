# ADR-0002：回环本地 Web 桌面应用

[English](0002-local-web-desktop.md)

- 状态：已接受
- 日期：2026-08-12

## 背景

受网络、CORS、私网访问和媒体能力限制，云端 HTTPS 页面中的浏览器 JavaScript 无法可靠直连私网 NVR。目标用户也不会维护 Docker 或 Home Assistant。

## 决策

发布一个 Windows 进程，同源提供 SPA 和 HTTP API，并打开回环地址。默认监听 `127.0.0.1`；LAN 模式是未来独立的安全功能。

## 影响

安装、签名成为产品责任；同时避开浏览器混合内容/CORS 死路，并将 NVR 凭据保留在本地。
