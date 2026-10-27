# MCP Tool Surface Audit

## 目的

本文记录 1.0 前 21 个已注册工具的用途、路由边界和第三方 agent 风险。路由说明已进入
全部工具的标准 MCP description；本文是审计索引，不替代 `tools/list` 或 README 的当前契约。

## 分层结论

| 层级 | 工具 | 结论 |
|---|---|---|
| 首选主入口 | `plan_stargazing_session` | 第三方 agent 应优先用于“去哪、哪天、看什么”的组合决策 |
| 兼容入口 | `get_best_stargazing_plan`、`get_multiday_stargazing_plan` | 继续服务已有 bbox-first 调用方 |
| 支撑能力 | celestial、weather、places、telescope 工具 | 用于精确问题、深入查询或主规划后的补充 |
| 发现/诊断 | `get_tool_catalog`、`get_local_datetime_info` | 用于能力发现和环境时间，不应替代业务规划 |

## 逐工具审计

| 工具 | Agent 应在何时使用 | 不应在何时使用 | 1.0 前关注点 |
|---|---|---|---|
| `plan_stargazing_session` | 需要跨一至七晚完成地点、时间、目标与设备的综合决策 | 只查询单项天气、天体位置或光污染事实 | 当前首选主入口；冻结契约前继续验证字段稳定性与长任务边界 |
| `get_best_stargazing_plan` | 已有 bbox、观测时间与时区，要比较区域内地点 | 只有一个坐标或只问单个天体位置 | 兼容单晚入口；保持现有参数和返回结构稳定 |
| `get_multiday_stargazing_plan` | 比较连续 1–7 个夜晚 | 需要更长周期、非连续日期或实时任务状态 | 兼容多日入口；保持现有参数和返回结构稳定 |
| `analysis_area` | 需要地点候选、分页或规划后的底层结果 | 已经只需要最终观测决策 | 保留同步兼容入口及 `db_config_path`；后台流程走任务工具，见任务生命周期文档 |
| `submit_area_analysis` | 区域地点搜索可能超过一次调用的等待时间 | 需要完整观测决策或已有活动任务只需查询 | 返回规范化请求；活动重复提交去重，终态重交可能命中缓存 |
| `get_area_analysis_task` | 已有任务编号，查询状态、失败、实际执行占用 | 需要读取结果页 | 逻辑终态与 `execution_pending` 分离，不能把取消等同线程停止 |
| `cancel_area_analysis_task` | 已提交任务不再需要继续发布结果 | 想删除缓存或中止其他业务 | 幂等逻辑取消；运行中的底层调用仍占配额 |
| `get_area_analysis_result` | 任务成功后按页读取结果 | 任务仍在排队/运行，仅需轮询 | 校验发布版本；缺失、过期、替换时引导重交，不偷偷重算 |
| `light_pollution_map` | 需要区域光污染网格或可视化数据 | 只想知道最终推荐地点 | 返回数据可能较大；未来需要更清晰的资源与数据版本语义 |
| `get_weather_by_name` | 只有地点文本，需要天气事实 | 需要完整观星决策 | `provider` 默认应由服务端管理；地点解析 provenance 需要进入 evidence |
| `get_weather_by_position` | 已有精确坐标，需要天气事实 | 需要比较多个观星地点 | `provider` 是高级诊断参数；需要统一 forecast freshness |
| `get_nightly_forecast` | 已有地点和夜晚，需要目标候选 | 已经需要设备适配的拍摄排序 | 输出应增加稳定 summary；目标策略应与 observation goal 对齐 |
| `get_telescope_targets` | 已知设备与地点，需要目标适配排序 | 只问肉眼或通用当晚目标 | 增加稳定设备 preset，减少 agent 手工填写光学参数 |
| `get_shooting_plan` | 已知设备、地点和日期，需要自动匹配目标并排单晚拍摄时间表 | 尚未决定日期或地点，或只需目标排名 | 工具自行匹配目标，不接收调用方指定的目标集合；连续窗口模型应复用 |
| `get_celestial_pos` | 查询单个天体在指定时刻的位置 | 规划整晚目标组合 | 保持原子能力；不扩展成组合规划入口 |
| `get_celestial_rise_set` | 查询单个天体的升落事件 | 需要完整可执行观测窗口 | `calendar_day` 与 `next_events` 路由说明要进入公开描述 |
| `get_moon_info` | 只需要月相、照明或月球位置 | 需要判断月光对具体目标的综合影响 | 保持事实工具；规划层负责解释影响 |
| `list_visible_planets` | 需要当前可见行星清单 | 需要设备与地点综合排序 | 保持轻量；明确“可见”阈值和时间语义 |
| `get_constellation` | 查询星座中心位置 | 识别任意坐标所属星座或做目标规划 | 工具名可能造成能力误读；公开描述需明确实际语义 |
| `get_local_datetime_info` | agent 需要服务器所在环境的当前时间与时区 | 用户已经给出观测地时区，或想知道远端地点时间 | “本地”相对谁必须写清；不应隐式替代用户地点时区 |
| `get_tool_catalog` | 客户端需要 wrapped catalog 元数据 | MCP 客户端已经只需标准 `tools/list` | 保持与 `tools/list` 一致；增加路由元数据前需先定义稳定 schema |

## 公共参数风险

### 基础设施泄漏

- `analysis_area.db_config_path`
- `get_best_stargazing_plan.db_config_path`
- `get_multiday_stargazing_plan.db_config_path`

处理原则：现有工具先保留兼容；新主入口不暴露；服务端通过环境或配置注入。

### Provider 选择

- `get_weather_by_name.provider`
- `get_weather_by_position.provider`
- planning 工具的 `weather_provider`

处理原则：`all` 继续作为兼容默认值；新主入口默认使用服务端策略，只在明确的高级诊断契约中允许覆盖。

### 低层地理输入

- planning 当前要求 `south/west/north/east`。

处理原则：精确 bbox 继续受支持；agent-native 入口还应支持地点文本或清晰的解析前置流程，并回显最终采用的坐标、datum 和 provenance。

## 已交付的工具路由说明

每个工具的标准 MCP description 已稳定包含：

- `Use when:`：适合解决的问题；
- `Do not use when:`：常见误选场景；
- `Requires:`：调用前必须掌握的信息；
- `Returns:`：agent 可以依赖的主要结构；
- `Follow-up:`：典型后续工具或资源。

说明直接写在工具 docstring 中；`plan_stargazing_session` 的显式 decorator description
优先于其 docstring。没有新增 `use_when` 等 catalog 字段，也没有改动输入、输出 schema
或历史基线。普通 catalog 条目的 `description` 继续保留首行摘要，完整说明由既有
`docstring` 提供；显式 description 自身已完整。

`tests/test_tool_routing.py` 通过 SDK 和真实 HTTP 发现验证全部工具的说明完整、catalog
能提供同一份完整描述，以及后续引用只指向已注册工具；另保护星座中心、服务器本地时间、
升落事件范围、行星地平线、兼容入口和任务工具的易误用边界。schema 兼容性仍由
`tests/test_public_schema_baseline.py` 与协议基线测试独立验证。

本轮发现快照和双客户端任务路由回归的证据见
`evaluations/reports/2026-10-27-tool-routing.md`。客户端回归仅代表三个任务工作流，
不扩展为 AI 已分别验证全部 21 个工具。
