# 1.0 公共契约与迁移说明

## 当前状态

本次冻结面向 `1.0.0` 的公共契约；包的发布版本仍以 `pyproject.toml` 为准，本次不创建
发布标签。响应 `_meta.version="1.0.0"` 是已有的 envelope 版本，不能据此判断安装包
已经发布到 1.0，也不能用它替代部署版本记录。

`tests/public_contract_v1.json` 独立保存全部 21 个工具的名称、参数与返回 schema、公开
注解、14 个详细请求/结果模型、错误码及默认/任务 envelope。原有 17 工具的
`tests/public_schema_baseline.json` 保留不动。SDK 与真实 HTTP `tools/list` 验证两份基线。

部分工具仍公布通用字典 outputSchema，望远镜结果也含共享依赖产生的字典；冻结记录其
真实声明，不虚构所有结果已经完整类型化。可依赖字段与单位见 README、详细模型和
既有执行/序列化测试；后续增加完整输出类型声明也须兼容审查。

## 兼容与弃用规则

机器可读副本是 [contract-policy.json](contract-policy.json)。以下期限是项目采用的规则，
不是对历史版本的统计：

1. `get_best_stargazing_plan` 和 `get_multiday_stargazing_plan` 继续支持；目前没有活跃
   弃用通知，保留期尚未开始。推荐新入口不等于旧入口已经弃用。
2. 正式弃用须在公开发布说明中同时给出受影响工具/字段、替代方案、请求/结果映射、
   首次通知版本与日期、最早移除版本和兼容测试。仓库草稿不启动保留期。
3. 通知后至少保留 **90 天**，并发布至少 **两个后续 minor 正式版本**；两项须同时
   满足。既有 1.x 契约的删除、重命名和不兼容变化只允许在 **2.0 或更后的 major**。
   到期不自动移除，仍须单独变更和发布审查。
4. 工具改名/删除、增加必填输入、删除已支持枚举值、改变默认值含义、单位、时区或已有
   字段/状态语义均是不兼容变化。文案澄清不能改变原有语义。
5. 新工具、可选输入/输出可作为兼容增量，但须明确默认/缺失语义并有文档和测试。当前
   精确快照门禁对这类增量也要求显式审查；不能批量刷新历史快照绕过门禁。
6. 调用方应容忍未知可选输出字段和新的非枚举诊断代码，保留原始错误；遇到未知任务
   状态不猜测成功，应停止自动动作并检查服务版本。冻结的输入/状态枚举受基线保护。

## 新调用方

完整的“去哪、哪晚、看什么、用什么设备”决策使用 `plan_stargazing_session`。
`request` 必须提供 `location` 与 `start_date`；地点只能选择 `place_name`、`center`、
`bounds` 其中一种。`time_zone` 默认 `Asia/Shanghai`，`nights` 默认 3；应显式填写实际
观测地时区与夜晚数量，不能拿服务器时区代替观测地时区。

`observation_style` 为 `balanced`、`deep_sky`、`visual`、`planetary` 或 `beginner`。
设备可省略，也可使用 `seestar_s50`、`hope_d60_asi2600mc_air` 或 `custom`；`custom`
必须提供 `overrides.focal_length_mm`。preset 可被 overrides 覆盖。不认识的请求字段会
被拒绝，不要自行添加 provider、数据库路径或未实现的 constraints 对象。

以下 JSON 保存成请求文件，再交给示例客户端。日期只演示格式，运行前应改为希望观测的
本地夜晚；这些示例不声称对应日期的天气或地点已在线核验。

### 地点文本与设备 preset

```json
{
  "location": {"place_name": "浙江省安吉县", "radius_km": 40},
  "start_date": "2026-11-01",
  "time_zone": "Asia/Shanghai",
  "nights": 3,
  "observation_style": "deep_sky",
  "equipment": {"preset": "hope_d60_asi2600mc_air"},
  "candidate_limit": 3,
  "target_limit": 5,
  "avoid_popular_spots": true,
  "prefer_quiet_at_night": true
}
```

```bash
uv run python examples/agent_planning_demo.py --request request.json \
  --url http://localhost:3001/shttp
```

客户端保留整个 envelope，成功但没有 decision 时仍输出 uncertainties 和 next_actions；
业务错误以非零退出码和原始结构化错误返回，不伪装成空候选。

### 精确 bbox 的单晚调用

```json
{
  "location": {"bounds": {"south": 30, "west": 119, "north": 31, "east": 120}},
  "start_date": "2026-11-01",
  "time_zone": "Asia/Shanghai",
  "nights": 1,
  "observation_style": "balanced",
  "candidate_limit": 3,
  "target_limit": 5
}
```

### 中心点与自定义设备

```json
{
  "location": {"center": {"lat": 30.6, "lon": 119.6}, "radius_km": 40},
  "start_date": "2026-11-01",
  "time_zone": "Asia/Shanghai",
  "nights": 1,
  "observation_style": "deep_sky",
  "equipment": {"preset": "custom", "overrides": {"focal_length_mm": 280}}
}
```

## 旧规划调用的迁移

| 旧字段/行为 | 新主入口 | 注意事项 |
|---|---|---|
| `south/west/north/east` | `request.location.bounds` | 保持原始坐标，不用地名解析替换精确区域 |
| 单晚 `time` | `start_date` 与 `nights=1` | 先确认观测地本地夜晚，不能直接截取 UTC 日期。旧入口按给定时刻规划，新入口按夜晚规划，窗口/排序不保证逐值相同 |
| 多晚 `start_date/nights` | 同名 request 字段 | 连续 1–7 晚，不是任意日期列表 |
| `time_zone` | `request.time_zone` | 保持观测地时区 |
| `candidate_limit/target_limit` | 同名 request 字段 | 控制返回预算，不等于内部召回数量 |
| `observation_style` 与热门/安静偏好 | 同名 request 字段 | 明确传入，不自动记忆单个用户习惯 |
| `weather_provider/db_config_path` | 无公共映射 | 新入口由服务端选择；需要指定 provider 或部署配置时保留原入口，不声称完全等价 |
| `max_locations/min_height_diff/road_radius_km/network_type` | 无逐项映射 | 新入口内部管理召回与成本；需要低层控制时保留兼容工具或单独地点工具 |

新结果不是旧字段的简单改名：`data.request` 回显默认值，`resolved_location` 回显采用的
地理输入；`decision` 给首选夜晚/地点/设备/目标，`alternatives` 给结构化比较。
`score_breakdown` 与理由用同一组因素。须共同消费 `evidence`、`uncertainties`、
`missing_inputs`、`would_change_if` 和 `next_actions`。没有候选时 `decision=null` 是合法
成功结果，不是工具异常。

冻结分数的定义和解释关系，不保证天气变化或排序改进后仍给出同地点、同数值。启发式
热门度与缺失道路/天气数据不能当成确认事实。缺失、`null`、空数组按模型定义处理，不
统一转换成零；现有 Unix 时间戳字段也不能一律当成 ISO 字符串。

## 地点分页与后台任务

同步 `analysis_area` 保留原查询分页语义。只需后台地点分析时使用提交、轮询、取页工具；
它们不提供完整观测决策。现有示例覆盖提交、重连、分页和显式取消：

```bash
uv run python examples/background_area_demo.py --south 30 --west 119 --north 31 --east 120
uv run python examples/background_area_demo.py --task-id RETURNED_TASK_ID --page 2 --page-size 1
uv run python examples/background_area_demo.py --task-id RETURNED_TASK_ID --cancel
```

`task_id` 是不透明执行编号，`resource_id` 是非分页查询编号，都不是永久数据版本。
同一活动查询复用任务，成功后重交可能命中缓存。成功任务绑定一次缓存 publication；
缓存缺失/过期/替换后返回 `TASK_RESULT_EXPIRED`，不偷偷重算或返回假空列表。
断线可继续任务，服务重启则丢失 registry；`TASK_RUNTIME_CHANGED` 要求重交规范化请求。
取消是幂等逻辑取消，线程仍可能占配额；检查 `execution_pending`，不能把取消当成物理
结束。状态接口成功不等于任务成功，须检查 `data.state/failure`。详见
[任务生命周期](task-lifecycle.md)。升落事件 `calendar_day/next_events`、分页编号和既有
错误码语义均不因冻结而重新解释。

## 升级前验证

```bash
uv run pytest tests/test_public_schema_baseline.py tests/test_v1_contract.py \
  tests/test_tool_routing.py tests/test_agent_planning_example.py tests/test_v1_planning_clients.py -q
```

1. 核对标准 `tools/list`、catalog、参数和路由说明，不只根据包版本推断。
2. 验证首选/备选、空候选、provider 降级、自定义设备、任务错误和分页恢复。
3. 三仓 wheel baseline/candidate 与本仓原生 CI 都须通过。MCP PR 用 core/SPF main
   wheels 核验最终消费者，不等同于修改另外两个仓库或重跑它们所有原生发布任务；
   跨仓变更仍须各自 PR 和完整检查。
4. AI 验收保留实际工具调用/返回证据；离线冻结数据通过不代表真实 provider uptime。

正式发版按独立流程进行；冻结和测试通过不自动创建 tag、PyPI 或镜像发布。
