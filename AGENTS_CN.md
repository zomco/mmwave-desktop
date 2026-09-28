# AI 协作者说明

[English](AGENTS.md)

修改仓库前必须完整阅读本文件，再按任务阅读对应资料。AI 生成的改动与人工改动遵守相同的评审、测试、安全和许可证要求。

## 项目使命

TraceCue 帮助非极客型公寓和小物业运营者更快找到相关 NVR 录像。必须保持以下不变量：

1. 主回查是直播流上的本地抓拍和短片（[ADR-0008](docs/architecture/decisions/0008-local-clip-review_CN.md)）。NVR 是可选冷存档，不是默认 seek 路径。
2. Desktop 服务默认只监听 `127.0.0.1`。
3. 媒体处理使用 FFmpeg 和浏览器视频能力，不在 Python 中解码或渲染视频。
4. 仅有 NVR 同源数据时，不得宣传为高置信降误报。
5. `desktop`、`gateway`、`engine` 共用单仓，但接口边界必须明确。
6. TraceCue 必须在没有 Home Assistant 时构建运行。唯一允许的毫米波运行时依赖是 `mmwave-engine` 包（[ADR-0008](docs/architecture/decisions/0008-local-clip-review_CN.md)）。不要导入 `mmwave-fusion`。
7. 历史传感器时间轴需要常驻生产者；按需启动的 desktop 无法补录错过的雷达历史。
8. `mmwave-engine` 是权重最高的视频标签。`tracecue-engine` 是冷存档时间线和离线参考，不是它的运行时助手。原始 NVR 标签不是训练真值（[ADR-0009](docs/architecture/decisions/0009-radar-tag-outranks-nvr_CN.md)）。

## 修改前

1. 查看 `git status`，保留用户的无关改动。
2. 阅读最近模块的中英文 `README`。
3. 阅读相关规范和已接受 ADR。
4. 修改公共契约时，同一改动内更新中英文文档、示例、schema 和测试。
5. 若改动与已接受边界冲突，先新增或更新 ADR，再实现。

## 文档路由

| 任务 | 首先阅读 |
| --- | --- |
| 产品范围或 UX | `docs/product/`，再读 `docs/architecture/boundaries_CN.md` |
| Desktop/API/NVR/媒体 | `desktop/README_CN.md`、HTTP API、海康兼容和打包文档 |
| Gateway/雷达采集 | `gateway/README_CN.md`、架构总览、timeline 规范 |
| Engine/Interval 逻辑 | `engine/README_CN.md`、[ADR-0009](docs/architecture/decisions/0009-radar-tag-outranks-nvr_CN.md)、timeline 规范 |
| CI/发布/安全 | `docs/operations/`、`CONTRIBUTING_CN.md`、`SECURITY_CN.md` |
| 跨仓毫米波研究 | `docs/architecture/boundaries_CN.md`；禁止建立运行时 import |

## 修改规则

- 中英文文档语义必须一致。英文使用 `.md`，中文使用 `_CN.md`。
- 内部时间统一为 UTC 毫秒；外部时间必须是带明确时区的 RFC 3339。
- 不得在 SQLite 或日志中保存密码、认证头或带凭据的 RTSP URI。
- FFmpeg 必须使用参数数组调用，禁止经过 shell 拼接。
- NVR 响应属于不可信输入；限制 XML/JSON 大小并禁用 XML 外部实体。
- 能力支持必须基于型号/固件的证据，不得假定所有海康设备行为一致。
- 使用稳定内部 ID，不以海康通道号或 trackID 作为业务主键。
- clip 是派生产物：先写 `.partial`，校验后再原子改名。
- 新依赖必须说明原因、检查许可证并评估个人维护成本。
- 未经所有者明确决策，不得修改 `LICENSE` 或接受新的贡献许可条款。

## 测试与完成标准

任何文档或结构改动都运行 `python scripts/ci/verify_repo.py`。模块清单文件落地后，再运行 `docs/development/testing_CN.md` 中的模块命令。交付时说明执行过什么，以及哪些硬件行为尚未验证。

只有实现、测试、中英文文档、契约/示例和迁移说明一致时，任务才算完成。不得把计划能力描述为已实现。

## 交接格式

较大任务结束时包含：

- 结果及影响的产品切片；
- 修改的文件/契约；
- 执行的命令与结果；
- 已知风险或未验证硬件行为；
- 下一项最小可执行工作。

长交接使用 `docs/ai/handoff_CN.md`。
