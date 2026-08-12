# 变更日志

[English](CHANGELOG.md)

首个实现里程碑后，所有重要变更都记录在这里。公共 API 或可分发应用出现后，发布版本遵循语义化版本规范。

## 未发布

- 接受 ADR-0004，并将单仓及包元数据统一为 MIT License。
- 固定按月保留的 BtbN FFmpeg 8.1 LGPLv3 Windows 构建、二进制/源码/许可证哈希及可复现获取校验。
- 将仅 GPL 构建提供的 `libx264` 转码回退替换为固定构建中已验证的 `libopenh264` 编码器。
- 建立单仓产品、架构、契约、AI 协作与 CI/CD 文档基线。
- 实现 Engine 时间轴核心和严格的 `timeline.v1` 校验。
- 实现具有输入边界和 fixture 测试的海康 ISAPI/RTSP 适配层。
- 实现 Desktop FastAPI/SQLite 服务、React/Vite UI、持久化作业、时间轴映射和 FFmpeg 出片流水线。
- 实现常驻 Gateway 核心，包含时钟健康、有界轨迹处理和持久导出。
- 增加精确依赖锁、模块 CI/安全自动化，以及显式门禁的 Windows 打包/签名/SBOM/冒烟流程。
