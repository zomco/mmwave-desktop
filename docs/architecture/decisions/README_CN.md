# 架构决策记录

[English](README.md)

| ADR | 状态 | 决策 |
| --- | --- | --- |
| [0001](0001-monorepo-first_CN.md) | 已接受 | 前期将 desktop、gateway 和 engine 保持在单仓 |
| [0002](0002-local-web-desktop_CN.md) | 已接受 | 主桌面形态使用只监听回环地址的本地 Web 应用 |
| [0003](0003-nvr-authoritative-media_CN.md) | 已接受 | NVR 保持为权威媒体存储 |
| [0004](0004-licensing-before-contributions_CN.md) | 已接受 | 整个单仓采用 MIT，并独立履行第三方许可证义务 |
| [0005](0005-initial-implementation-stack_CN.md) | 待决 | 采用初始 Python/FastAPI、React/TypeScript 与 FFmpeg 技术栈 |
| [0006](0006-temporary-lan-clip-sharing_CN.md) | 已接受 | 允许用户显式开启仅限单个已生成片段、带令牌的临时局域网分享 |
| [0007](0007-event-scoped-visual-validation_CN.md) | 已接受 | 对有界 NVR 事件窗口增加可选的本地视觉验证 |
| [0008](0008-local-clip-review_CN.md) | 已接受 | 主回查是本地抓拍/短片；NVR 是冷存档 |
| [0009](0009-radar-tag-outranks-nvr_CN.md) | 已接受 | 雷达标签权重大于 NVR 标签；tracecue-engine 是离线参考 |

ADR 使用不可变编号。若要改变已接受结论，应新增 ADR 取代，而不是静默改写原结论。
