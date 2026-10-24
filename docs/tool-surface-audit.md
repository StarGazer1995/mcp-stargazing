# MCP Tool Surface Audit

## 目的

本文记录 1.0 前 16 个已注册工具的用途、路由边界和第三方 agent 风险。它是迁移审计，不替代 `tools/list` 或 README 中的当前契约。

## 分层结论

| 层级 | 工具 | 结论 |
|---|---|---|
| 当前主入口 | `get_best_stargazing_plan`、`get_multiday_stargazing_plan` | 应优先用于“去哪、哪天、看什么”的组合决策 |
| 支撑能力 | celestial、weather、places、telescope 工具 | 用于精确问题、深入查询或主规划后的补充 |
| 发现/诊断 | `get_tool_catalog`、`get_local_datetime_info` | 用于能力发现和环境时间，不应替代业务规划 |

## 逐工具审计

| 工具 | Agent 应在何时使用 | 不应在何时使用 | 1.0 前关注点 |
|---|---|---|---|
| `get_best_stargazing_plan` | 已有 bbox、观测时间与时区，要比较区域内地点 | 只有一个坐标或只问单个天体位置 | 当前主入口；移除新入口中的部署参数，补决策、备选、证据与分数分解 |
| `get_multiday_stargazing_plan` | 比较连续 1–7 个夜晚 | 需要更长周期、非连续日期或实时任务状态 | 当前多日入口；补设备约束、连续窗口和跨夜差异解释 |
| `analysis_area` | 需要地点候选、分页或规划后的底层结果 | 已经只需要最终观测决策 | `db_config_path` 属于基础设施泄漏；长任务和缓存新鲜度语义待补 |
| `light_pollution_map` | 需要区域光污染网格或可视化数据 | 只想知道最终推荐地点 | 返回数据可能较大；未来需要更清晰的资源与数据版本语义 |
| `get_weather_by_name` | 只有地点文本，需要天气事实 | 需要完整观星决策 | `provider` 默认应由服务端管理；地点解析 provenance 需要进入 evidence |
| `get_weather_by_position` | 已有精确坐标，需要天气事实 | 需要比较多个观星地点 | `provider` 是高级诊断参数；需要统一 forecast freshness |
| `get_nightly_forecast` | 已有地点和夜晚，需要目标候选 | 已经需要设备适配的拍摄排序 | 输出应增加稳定 summary；目标策略应与 observation goal 对齐 |
| `get_telescope_targets` | 已知设备与地点，需要目标适配排序 | 只问肉眼或通用当晚目标 | 增加稳定设备 preset，减少 agent 手工填写光学参数 |
| `get_shooting_plan` | 已知设备、地点和目标集合，需要单晚时间表 | 尚未决定日期或地点 | 与多日 planning 的边界需明确；连续窗口模型应复用 |
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

## 工具路由元数据目标

每个工具的公开描述最终应稳定包含：

- `use_when`：适合解决的问题；
- `do_not_use_when`：常见误选场景；
- `requires`：调用前必须掌握的信息；
- `returns`：agent 可以依赖的主要结构；
- `follow_up`：典型后续工具或资源。

在为 `get_tool_catalog` 增加这些字段前，必须先确认 FastMCP `tools/list` 能提供等价、可测试的标准描述，避免维护第二套只在自定义 catalog 中可见的路由协议。
