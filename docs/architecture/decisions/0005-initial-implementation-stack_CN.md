# ADR-0005：初始实现技术栈

[English](0005-initial-implementation-stack.md)

- 状态：待决
- 日期：2026-08-12

## 背景

产品由一位所有者在大量 AI 协助下维护。技术栈需要支持快速迭代、可读契约、Windows 打包、确定性测试和子进程媒体处理，同时不能把视频处理责任塞进 Python。

## 建议决策

- Desktop 后端：Python 3.12 + FastAPI；
- Desktop 前端：React + TypeScript + Vite；
- Engine：低依赖 Python 包，可脱离 FastAPI/HA 使用；
- Gateway：初期使用 Python，硬件适配器与 engine 隔离；
- 持久化：SQLite + 显式迁移；
- 媒体：固定版本 FFmpeg/FFprobe，以子进程调用；
- 打包：one-folder Windows 应用和按用户安装器。

## 影响

该技术栈易上手、契约友好，但 Python 打包和 Windows 签名需要有意识的自动化。前后端版本兼容必须随同一安装包管理，而不是作为两个独立部署协调。选择低功耗 Gateway 硬件前，必须测量资源限制。

## 接受条件

M1 建立可运行骨架、锁定依赖、Windows/Linux 测试和明确打包/版本策略后接受本 ADR。若探针暴露重大阻碍，应在代码规模扩大前取代本提案。

## 实现证据

0.1.0 基线已经采用本提案技术栈，包含精确 npm/Python 开发锁、模块测试和 Windows one-folder/安装器策略。本 ADR 在托管 Windows/Linux CI 完成，且使用获批 FFmpeg 与签名输入构建并冒烟测试受门禁保护的软件包前仍保持“待决”。
