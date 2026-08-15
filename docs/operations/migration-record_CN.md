# 项目资料迁移记录

[English](migration-record.md)

- 迁移日期：2026-08-12
- 目标：`D:\Users\zomco\Documents\GitHub\tracecue`
- 来源上下文：在 `mmwave-workspace` 及三个 Lab 子模块旁形成的产品/架构决策。

## 已迁移内容

- TraceCue/Clipmark 产品问题、目标客户、价值和非目标；
- Desktop/Gateway/Engine 产品和部署边界；
- NVR 权威媒体架构及 FFmpeg 策略；
- 海康能力风险和兼容证据模型；
- HTTP API、SQLite/领域模型和 `timeline.v1` 草案；
- Windows 打包、CI/CD、安全、验证和 UX 指导；
- AI 协作规则、交接格式和开发者贡献指南；
- 商业/开源/渠道假设和命名状态。

## 未迁移内容

此前 `mmwave-workspace` 中没有 TraceCue 源代码。没有复制 `mmwave-*` 源码、Git 历史、运行时子模块或 Home Assistant 依赖。这些仓库继续作为 Lab，并通过明确契约产生 fixture/导出。

## 事实来源变化

从本次迁移开始，TraceCue 产品决策归本仓库文档/ADR 管理。`mmwave-workspace` 只继续作为跨仓 Lab 测试和研究的事实来源。聊天历史不是持久事实来源。

## 后续

ADR-0004 已于 2026-08-12 接受，单仓现使用 MIT。若后续历史资料与已接受 ADR 冲突，应新增取代 ADR，而不是静默混合假设。

## 0.1.0 实现迁移

可执行代码现会在首次启动时初始化 Desktop SQLite schema version 1。新数据库创建文档约定的 NVR、能力、通道、来源、空间/绑定、Interval、录像段、作业、片段和导入表。此前没有可执行数据库需要迁移。重启时，未完成的 `running` 作业会改为 `interrupted`；系统不会猜测媒体工作已经完成。

Gateway 为常驻 Interval 和有界诊断维护独立内部 SQLite。Desktop 永不读取该数据库；数据通过 `timeline.v1` 跨越边界。

### Desktop schema v2-v6

Schema v2 新增历史筛选/检索结果、只读 NVR 事件审计证据、事件 JPEG 预览和 Clip 来源。Schema v3 新增实测 NVR UTC 偏移、历史筛选的多 NVR 摄像机范围、会过期的通道截图和缓存事件 WebP 动图。已有筛选继续使用原摄像机列表，已有 Interval/Clip 的 UTC 时间戳不改变；已有 NVR 行在重新探测写入显式偏移前，会回退解析已保存的 POSIX 时区。由于回放参数映射发生变化，schema v4 会使旧 JPEG 预览缓存失效；后续按需重新生成，不会改动 NVR 原始录像。

Schema v5 新增本地 Trace 会话、有界检索迭代、迭代与作业关联及逐会话事件审阅状态。它只保存稳定本地 ID、归一化事件标签和 UTC 毫秒，不保存 NVR 凭据、Authorization header 或回放 locator。已有检索与派生媒体不变。设置记录增加仅用于构造浏览器夜间时间窗的本机 `night_start_hour` 和 `night_end_hour` 默认值。

2026-08-13 事件检索兼容更新不改变 SQLite schema。新检索使用有界历史报警日志，不再把连续录像文件当作事件。请求校验现在只接受 `motion`、`video_tamper`、`line_crossing`、`region_intrusion`；旧会话/筛选中的 `continuous` 或兜底 `smart` 标签为审计历史继续保留，但浏览器在复用前会丢弃。缓存事件审计 JSON 升级为 schema `2` 并进行一次只读刷新，使 Smart 规则端点使用摄像机外部通道 ID，而不是码流 track ID。已有 Interval、Clip 与 NVR 媒体均不改变。

2026-08-14 单摄像机/两阶段检索更新同样保持 SQLite schema v5。新的检索与历史筛选请求要求恰好一个摄像机和至少一种规范事件类型。新 Trace 会话只接受一个不同时间窗；旧多迭代会话继续可读，但浏览器不再恢复。结果摘要增加密度、时长和事件类型构成，且不会加载事件媒体。新历史事件会配对报警开始/停止日志，并把时长证据写入 `attributes_json`；已有一秒索引行不会被改写，在新检索重新观测前显示“时长未知”。事件审计 JSON 升级为 schema `4` 并只读刷新，以修正有实证的 LineDetection 与 FieldDetection 坐标。新 Clip 会把设备返回的回放 locator 重新限制到已解析请求片段，并把公开时间标注为 NVR 索引时间；已有 Clip 和 NVR 原始录像均不改变。

随后 2026-08-14 的时间轴/设备详情细化仍不需要数据库迁移。新请求要求恰好一种事件类型。结果摘要以有界逐事件区间替代小时密度/类型分面，供前端缩放、点击和拖放选择；事件时长分组按所选重叠时间窗重新计算。新候选片段只在同一检索/摄像机的相邻非重叠事件中点裁剪前后上下文，已有片段不重写。设备软硬件详情按需读取且不持久化；设备未提供的摄像机身份字段保持为空。

Schema v6 把未被用户修改过的旧片段上下文默认值从前滚 5 秒/后滚 10 秒改为零，使新事件候选严格匹配索引事件区间。显式修改过的非默认设置和已有片段均不改变。媒体状态响应现会暴露作业阶段进度，不新增数据库列。ADR-0006 为就绪片段增加只存内存、有效 15 分钟的局域网分享令牌；令牌、局域网 URL 和二维码均不持久化。

后续摄像机加载/活动模式筛选细化不需要数据库迁移。已有就绪截图在下一次成功刷新后成为十分钟 stale-while-revalidate 缓存；已过期但验证过的文件会在一个刷新作业运行期间继续可读。结果活动簇与精确时长边界在查询时从已有 UTC 区间派生，不持久化目标身份、目标坐标或推断物体类别。
