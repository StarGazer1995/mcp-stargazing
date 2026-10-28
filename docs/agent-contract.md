# 第三方 Agent 契约方向

## 状态

本文定义 `mcp-stargazing` 面向第三方 AI agent 的公共契约与演进约束。已实现的 1.0
冻结面记录在 `tests/public_contract_v1.json`；未来方向不构成未实现字段的承诺。当前工具、
参数和返回值仍以 `tools/list`、`get_tool_catalog` 和 README 为准，并受冻结测试保护。

现有工具的 1.0 前 schema 已保存并受协议测试保护，见
[公共 schema 基线](public-contract-baseline.md)。该快照用于审查兼容性变化，不等同于
冻结 1.0；新的独立 1.0 快照补齐长任务等后续能力，不改写该历史记录。完整范围、
兼容保留期限和可运行示例见 [1.0 迁移说明](v1-migration.md)。冻结不自动触发发版。

## 北极星目标

一个不了解仓库内部结构的第三方 agent 应当能够：

1. 从工具描述中选择正确入口；
2. 用用户意图而不是部署细节表达请求；
3. 在一次主规划调用后得到首选方案、备选方案和可核查依据；
4. 区分事实、启发式推断、缺失数据和降级结果；
5. 在部分 provider 失败时继续工作，并知道下一步可以做什么；
6. 在服务升级后继续稳定消费未弃用的字段。

## 工具分层

字段含义、时间范围、降级判读与标准 MCP 请求示例见
[外部 AI 规划结果判读指南](planning-result-guide.md)。这些关键约束必须同时进入标准
`tools/list` description；仓库文档不能替代 AI 实际读取到的说明。

### 主决策入口

当前首选主入口是：

- `plan_stargazing_session`

以下入口为现有 bbox-first 调用方继续保留：

- `get_best_stargazing_plan`
- `get_multiday_stargazing_plan`

`plan_stargazing_session` 已在输入、输出、迁移评审、10 个 golden scenarios 和两个第三方
agent 客户端代表性黑盒验收通过后注册。旧入口至少保留一个有文档的迁移周期，避免现有调用方
被迫立即迁移。

主入口负责回答：

- 哪个夜晚更合适；
- 哪个地点更合适；
- 适合看什么或拍什么；
- 可执行的连续观测窗口是什么；
- 为什么第一名优于备选项；
- 哪些变化可能推翻当前推荐。

规划天气必须绑定所选夜晚的逐小时预报，不得用查询时当前天气或日均值代替。
天气 evidence 的 facts 记录 provider、时区化的统计起止、可用预报时次与云层统计；
缺失、超出时效和部分覆盖须进入 notes/uncertainties。完全没有可用时段时不得给天气
晴朗驱动项；`nightly_weather_unavailable` 与 `no_usable_observation_window` 为高不确定性。
降级结果中的首选地点/夜晚只是条件性排序，不能解释为已验证可出行。
七天及更远的预报另标记 `long_range_forecast`，提示临近出发重查；这是一项保守提示策略，
不是对特定天气模型精度的保证。
多晚调用可复用原始天气快照，但每晚必须独立取时段、计算分数；缓存仅限一次请求。

中心点加半径是区域搜索，不锁定具体观测点；安静度/热门度是启发式且由偏好开关启用。
既有 `night_window` 保留民用暗夜（太阳高度 −6°）语义，不能把其时长称为天文黑夜或
保证的深空拍摄时长。公共工具/schema 基线保持不变，不通过刷新快照隐藏行为修复。

### 支撑工具

支撑工具提供地点、天气、天体和设备维度的深入查询。它们可以被 agent 单独调用，也可以由应用服务组合：

- 地点：`analysis_area`、`light_pollution_map`
- 天空：`get_nightly_forecast`、天体位置与升落工具
- 天气：`get_weather_by_name`、`get_weather_by_position`
- 设备：`get_telescope_targets`、`get_shooting_plan`

### 诊断与发现工具

- `get_tool_catalog` 用于程序化检查工具元数据。
- 低层工具不能依赖调用方理解仓库内部模块、provider 实现或服务器文件系统。

### 已交付的路由说明

全部公开工具的标准 MCP description 已包含 `Use when:`、`Do not use when:`、`Requires:`、
`Returns:` 和 `Follow-up:`。它们说明适用问题、误用边界、必要上下文、可依赖的返回内容和
后续工具。显式 decorator description 优先；否则使用函数完整 docstring。

`get_tool_catalog` 沿用现有字段：普通工具的 `description` 是首行摘要，完整说明在
`docstring`；显式 description 已经包含完整说明。SDK 与真实 HTTP 测试保护发现面的说明及
后续工具名称。这里不新增第二套路由字段，也不改变参数或响应 schema。

## 公共参数边界

第三方 agent 应表达用户意图，而不是服务器部署方式。

### 应当成为公共输入

- 地理意图：地点文本、中心点与半径、或精确 bbox；
- 时间意图：指定时刻、日期范围、连续夜晚数量；
- 观测目标：深空摄影、目视、行星、入门等；
- 设备：稳定 preset 或显式光学参数；
- 用户约束：候选数量、连续晴朗时长、道路可达性、热门度偏好；
- 结果预算：返回多少候选、多少目标、是否需要详细证据。

`candidate_limit` 表示最终返回的排序候选数量；服务端可以在不改变响应预算的情况下评估更宽的
召回池，避免静态地点评分在天气评估前把潜在优胜者截掉。召回池会先做低成本天气粗排，
再对内部 Top N 执行夜景窗口与目标预报计算；这些成本控制细节不改变第三方 agent 的参数或响应契约。
服务端还可以复用 `stargazing-core` 的空间云量网格做一次区域级比较，再进入地点级精排；
空间模型不可用时会降级为地点级天气，不要求 agent 改写请求。

返回的观测窗口以小时预报为基础：服务端只在民用暗夜内合并时间连续、云量/降水/风况可执行的
小时段，并用月面照明和目标可用的中天高度做轻量调整。`start_time` 及现有天气字段保持兼容；
`end_time`、`duration_hours` 和 `quality_score` 是可选的增量字段，缺少连续预报时仍可退回单小时。

稳定设备 preset：

| preset | 焦距 | 口径 | 传感器 | 像元 | 默认架台 |
|---|---:|---:|---:|---:|---|
| `seestar_s50` | 250 mm | 50 mm | 未固化 | 2.9 µm | `altaz` |
| `hope_d60_asi2600mc_air` | 280 mm | 60 mm | 23.5 × 15.7 mm | 3.76 µm | `equatorial` |

preset 的任一光学字段都可通过 `overrides` 显式覆盖。HOPE D60 + ASI2600MC Air preset
只固化望远镜与主传感器参数；用户未提供架台时按常规深空摄影配置使用 `equatorial`，实际使用
经纬仪时应覆盖为 `altaz`。

### 不应成为默认公共输入

- `db_config_path` 等服务器文件路径；
- provider 认证信息；
- 缓存目录、线程数、数据库连接池等运行参数；
- 仅用于部署或调试的 provider 选择。

现有工具为兼容性可能暂时保留部分此类参数。它们属于待迁移债务，不应继续扩散到新的主入口。

## 目标响应结构

长任务：`submit_area_analysis`、`get_area_analysis_task`、`cancel_area_analysis_task` 与
`get_area_analysis_result` 提供应用层区域分析任务，详见 [任务生命周期](task-lifecycle.md)。
`_meta.task_id` 关联任务；未知运行进度不填 `_meta.progress`，数据中的 `progress` 为 `null`。
`execution_pending` 独立表达实际工作尚未释放，`result_revision` 绑定一次缓存发布，
防止旧任务读取被替换的结果。原有工具的默认响应格式与同步调用方式保持兼容。

主规划结果当前冻结以下语义，字段和嵌套模型由独立 1.0 基线保护：

```json
{
  "decision": {},
  "alternatives": [],
  "score_breakdown": {},
  "evidence": [],
  "uncertainties": [],
  "missing_inputs": [],
  "would_change_if": [],
  "next_actions": []
}
```

约束如下：

- `decision` 给出当前首选，而不是只返回排序列表；
- `alternatives` 解释备选项与首选项的关键差异；
- `score_breakdown` 必须能映射回实际排序因子；
- 复合规划向 SPF 请求地点时固定关闭 `avoid_popular_spots` 和 `prefer_quiet_at_night`，
  `place_base_score` 不含热门度偏好调整；SPF 仍提供热门度启发式字段，MCP 按用户请求
  在 `popularity_adjustment` 中计权一次。粗排与最终评估分别从同一基础分重算，不累加粗排分；
- `query.analysis_resource_id`（主入口为地点 `evidence.resource_id`）指向关闭上述偏好的
  地点查询；重查时保留其余地点搜索参数和半径。请求回显仍保留用户原始偏好；
- `score_breakdown.factor_contributions` 返回带符号的地点、天气、热门度和便利性贡献，推荐理由
  只应解释这些实际参与排序的信号；天气窗口、空间云量和月光等子信号也必须在有影响时可见；
- `evidence` 包含来源、获取时间、适用时间和必要的资源关联；
- `uncertainties` 明确区分启发式信号与观测事实；
- `missing_inputs` 只列出会实质影响决策的缺失条件；
- `would_change_if` 描述可能造成排名反转的条件；
- 人类可读文案不能替代结构化枚举和数值字段。

## 内部边界

目标调用链是：

```text
MCP tool wrapper
  -> application service
    -> domain calculation / provider adapter
```

- MCP wrapper 负责参数、公共 schema、响应 envelope 和错误翻译；
- application service 负责组合地点、天气、目标和设备能力；
- domain/provider 层负责具体计算与外部数据访问；
- application service 不应通过另一个 MCP wrapper 的 `.fn` 作为长期内部接口。

当前 planning 已通过独立 application service 和无 envelope 的内部 capability 完成组合，
生产代码不再调用其他 MCP wrapper 的 `.fn`；契约测试会阻止该耦合重新出现。

## 主入口决策与迁移计划（2026-10-24）

选择新增 `plan_stargazing_session`，而不是把现有两个 planning 工具原地扩展成大量互斥参数。
原因是新入口要表达地点文本、日期范围、设备 preset、用户约束和结构化证据；把这些直接
塞进 bbox-first 的旧签名，会让第三方 agent 难以判断哪些参数组合有效，也会扩大兼容风险。

迁移分四步：

1. 先在 application service 内完成 agent-native 请求与响应模型，不注册新 MCP 工具；
2. 用 golden scenarios 和至少两个第三方 agent 客户端验证工具选择、首次调用成功率、排序与降级；
3. 验收通过后注册 `plan_stargazing_session`，README 将其标记为首选入口，现有
   `get_best_stargazing_plan` 与 `get_multiday_stargazing_plan` 保持兼容；
4. 只有在新入口覆盖旧场景、迁移文档发布并至少经历一个有文档的弃用周期后，才考虑
   弃用旧入口；删除或重命名留到后续 major 版本。

第 1、2、3 步已经完成：`AgentPlanningRequest` 支持地点文本、中心点加
半径和精确 bbox，`AgentPlanningResult` 提供 decision、alternatives、精确评分分解、证据、
不确定性、关键缺失输入、排名反转条件和下一步动作。Seestar S50、HOPE D60 +
ASI2600MC Air 和 custom optics 会先归一化，再对首选 session 做设备目标匹配；provider 和
数据库路径不进入请求模型。10 个冻结 golden scenarios 全部通过，Codex CLI 与 Claude Code
在代表性 HOPE D60 + ASI2600MC Air 场景中均首次选择正确工具、首次实际调用成功并返回正确
答案。`plan_stargazing_session` 已作为第 17 个公开工具注册；两个旧 planning 入口继续保持
兼容，尚未进入弃用周期。

## 版本与弃用策略

1. 冻结后任何公共契约变化均须显式兼容审查，不通过刷新历史快照掩盖变化。
2. 1.x 的工具重命名、必填参数增加、枚举删除、默认/单位/时区和字段语义变化均是不兼容变化。
3. 正式通知后至少保留 90 天并发布两个后续 minor 正式版本，且移除只允许在 2.0 或更后
   major。两个旧规划入口仍受支持，没有活跃通知；推荐主入口不会自动启动弃用期。
4. 增量字段必须有稳定默认值；缺失与 `null` 的语义必须写清楚。
5. `tools/list`、`get_tool_catalog`、README 和契约测试必须同步。

规则的权威说明见 [1.0 迁移说明](v1-migration.md)，机器可读策略为 `docs/contract-policy.json`。

## 黑盒 Agent 验收场景

### 场景 A：多日深空摄影规划

用户意图：“未来三天上海周边用 Seestar S50 去哪里拍？”

验收点：

- agent 选择主规划入口；
- 不要求用户选择天气 provider 或提供数据库路径；
- 地点文本可以被解析，或工具明确返回需要的地理信息；
- 返回日期、地点、连续窗口、目标和备选方案；
- 解释第一名优于第二名的主要因素；
- 标出天气更新时间和 popularity 的启发式性质。

### 场景 B：天气 provider 部分失败

验收点：

- 整体调用不因一个 provider 失败而丢失所有候选；
- agent 能区分“无数据”和“不适合观测”；
- 响应给出可执行的下一步，而不是只返回内部异常。

### 场景 C：约束不足

验收点：

- 工具不伪造出发地、设备或驾驶时间；
- `missing_inputs` 只包含会改变决策的关键条件；
- 即使缺少可选信息，也能返回带不确定性说明的基础方案。

### 场景 D：长时间区域分析

验收点：

- agent 可以识别任务仍在运行；
- 进度、任务标识和最终资源之间的关系稳定；
- 超时不等价于业务失败；
- 恢复或重试不会无意中创建语义不同的查询。

## 当前非目标

- 在 Agent Contract 基线完成前大规模增加 ISS、卫星、流星雨或日食工具；
- 把某个个人用户的隐式偏好写入全局排序；
- 把第三方 agent 变成 provider、数据库或缓存实现的运维者；
- 用自然语言解释代替结构化证据和评分因子。


### Evidence-gated observing recommendations

Only candidates with the requested night's dated weather and a usable observation window
compete for the selected session and its alternatives. Unknown weather is not replaced by
an assumed score and is not classified as bad weather. Known forecasts without a usable
window are also excluded, with a distinct reason. If none qualify, the primary planner
returns `decision=null`, no alternatives, explicit uncertainties and next actions.
Known place, sky and generic target facts remain in `evidence` entries whose source is
`unranked_planning_reference`; `facts.status` is `weather_unknown` or `no_usable_window`.
These entries have no session score or comparison to the decision. Equipment configuration
is retained as evidence when supplied; reference targets are generic, not equipment-matched.

Compatibility planners retain reference candidates and notes, but leave recommended-place
and best-night summary fields null when no session qualifies. Their numeric weather fields
remain schema-compatible: absent weather has zero base score, contribution and weight as
placeholders, not a claim of bad weather. Place weights are not renormalized. Reference
candidate scores and positions must not be interpreted as an observing-session ranking.
Successful execution still means only that the request was processed.
