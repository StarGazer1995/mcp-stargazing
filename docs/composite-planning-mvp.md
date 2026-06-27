# 组合规划 MVP 接口设计

## 定位

`get_best_stargazing_plan` 是 `mcp-stargazing` 的第一个组合规划工具。它不引入新的下层能力，而是把现有的零散工具（地点搜索、天气、夜间目标）编排成一次"今晚去哪看什么"的组合查询，输出 agent-friendly 的排序建议。

## MVP 目标

- 输入：观测区域（bbox）+ 观测时间（ISO + IANA timezone）
- 下层：候选地点搜索（`analysis_area`）
- 上层：天气摘要 + 夜间目标摘要 + 排序打分 + 中文解释字段
- 输出：带排名的候选地点列表，每个地点附带推荐原因

## 逻辑边界

### 属于 `stargazing-place-finder`（下层）

下层的职责以地点搜索为中心，**不感知组合规划**：

- 根据 bbox 搜索候选观星地点
- 计算每个地点的光污染等级、道路可达性、综合评分
- 返回标准化地点列表

### 属于 `mcp-stargazing`（上层）

上层负责全部组合编排逻辑：

- 调用 `analysis_area` 获取地点候选
- 对每个候选地点并发调用 `get_weather_by_position` + `get_nightly_forecast`
- 从天气数据中提取最佳观测窗口
- 从夜间目标数据中提取月相与优先目标
- 计算综合推荐得分
- 生成中文推荐理由
- 排名、去重、输出结构化响应

## 输入参数

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `south` | float | 是 | — | 南边界纬度 |
| `west` | float | 是 | — | 西边界经度 |
| `north` | float | 是 | — | 北边界纬度 |
| `east` | float | 是 | — | 东边界经度 |
| `time` | str | 是 | — | 观测时间，ISO 8601 或 `YYYY-MM-DD HH:MM:SS` |
| `time_zone` | str | 是 | — | IANA 时区，如 `Asia/Shanghai` |
| `candidate_limit` | int | 否 | 3 | 最多评估的地点数 |
| `target_limit` | int | 否 | 5 | 每个地点推荐的优先目标数 |
| `weather_provider` | str | 否 | `"all"` | 天气数据源，传递给天气工具 |
| `max_locations` | int | 否 | 10 | 底层分析搜索的最大候选数 |
| `min_height_diff` | float | 否 | 100.0 | 最小高程差 |
| `road_radius_km` | float | 否 | 10.0 | 道路搜索半径 |
| `network_type` | str | 否 | `"drive"` | 道路网络类型 |
| `db_config_path` | str | 否 | None | 数据库配置文件路径 |

## 输出 schema

### 顶层结构 `BestStargazingPlan`

```json
{
  "query": { ... },
  "summary": { ... },
  "candidates": [ ... ]
}
```

### `PlanningQuery` — 回显归一化后的查询参数

包含所有输入参数 + `analysis_resource_id`（指向底层 `analysis_area` 搜索，agent 可据此翻阅全部地点结果）。

### `PlanningSummary` — 规划运行摘要

| 字段 | 说明 |
|------|------|
| `generated_at` | 生成时间（UTC ISO 字符串） |
| `requested_time` | 请求的观测时间 |
| `time_zone` | 请求的时区 |
| `total_candidates` | 返回的候选地点数 |
| `recommended_location_name` | 排名第一的地点名称 |
| `warnings` | 全局降级警告（如天气查询失败） |

### `PlannedLocationCandidate` — 单个候选地点

| 字段 | 说明 |
|------|------|
| `rank` | 排名（1-based） |
| `recommendation_score` | 综合推荐得分（0–100） |
| `recommendation_reasons` | 中文推荐理由（最多 5 条） |
| `location` | `StargazingLocation` 地点详情 |
| `weather_summary` | 浓缩版天气摘要（可能为 null） |
| `best_observation_window` | 最佳观测时段（可能为 null） |
| `moon_phase` | 月相名称 |
| `moon_illumination` | 月面照明比例 |
| `top_targets` | 推荐天文目标列表 |
| `notes` | 降级说明（如"天气摘要降级处理"） |

## 组合流程

```
get_best_stargazing_plan
│
├─ 1. 参数校验
│   ├─ 坐标合法性（south < north, west < east）
│   ├─ 正整数校验（candidate_limit, target_limit, max_locations）
│   └─ 时间解析校验
│
├─ 2. 地点搜索
│   └─ analysis_area.fn(south, west, north, east, max_locations, ...)
│       → 获取候选地点，按底层评分排序
│       → 截取前 candidate_limit 个
│
├─ 3. 并发评估（每个候选地点）
│   └─ asyncio.gather(
│       ├─ get_weather_by_position.fn(lat, lon, provider)
│       │   → 天气摘要 + 逐小时预报
│       │   → 提取最佳观测窗口（12h 内，云量最低、降水最少）
│       │
│       └─ get_nightly_forecast.fn(lon, lat, time, time_zone, limit)
│           → 月相 + 深空目标 + 行星
│           → 提取 top N 优先目标
│     )
│
├─ 4. 综合打分
│   ├─ 地点评分（底层 stargazing_score）× 0.65
│   ├─ 天气评分（云量、能见度、风速）× 0.35
│   ├─ 月光惩罚（月面照明 > 70% 时扣分）
│   └─ 降水概率惩罚
│
├─ 5. 生成推荐理由（中文）
│   ├─ 波特尔等级
│   ├─ 云量 / 能见度
│   ├─ 最佳观测时段
│   ├─ 月面照明比例
│   └─ 优先目标名称
│
└─ 6. 排序并返回
    └─ 按 recommendation_score 降序
    └─ 重新编号 rank
    └─ 收集全局 warnings
```

## 打分算法

```
推荐得分 = 地点评分 × 0.65 + max(0, 天气评分) × 0.35

地点评分 = location.score（下层综合评分，0–100）

天气评分 = 100 - 云量%                            # 云量基础分
          + min(20, 能见度km × 1.5)               # 能见度加分
          - max(0, min(20, (风速kph - 20) × 1.2)) # 大风扣分
          - 降水概率% × 10                         # 降水扣分

月光惩罚（独立于天气评分）:
  如果月面照明 > 70%: 天气评分 -= (照明% - 70%) × 25

最终得分 clamp 到 [0, 100]
```

## 降级行为

组合规划工具的核心原则是**部分成功优于全部失败**：

| 场景 | 行为 |
|------|------|
| 底层 `analysis_area` 失败 | 整体返回 error |
| 某个候选地点的天气查询失败 | 该地点的 `weather_summary` 为 null，`notes` 中记录降级原因；不影响其他地点 |
| 某个候选地点的目标查询失败 | 该地点的 `top_targets` 为空，`notes` 中记录降级原因；不影响其他地点 |
| 两个子查询均失败 | 地点仍在候选列表中，但 `weather_summary` 和 `top_targets` 均为空，得分仅基于地点评分 |

降级信息同时反映在两个层级：

- `summary.warnings`：跨候选地点的去重警告
- `candidate.notes`：每个地点的个别降级说明

## 边界情况

| 输入 | 预期行为 |
|------|---------|
| 无候选地点 | `total_candidates: 0`，`candidates: []`，`recommended_location_name: null` |
| `candidate_limit=1` | 返回 1 个候选地点 |
| bbox 跨越 180° 经线 | 由 `analysis_area` 的下层判定，当前不做特殊处理 |
| 时间在过去 | 照常执行（天气数据可能不可用，触发降级） |
| 时区无效 | 时间解析失败 → `INVALID_TIME_FORMAT` |

## 已知限制

1. **候选地点上限固定**：`candidate_limit` 决定了最多评估几个地点，不会自适应区域大小
2. **天气数据时效**：依赖外部 API，缓存在 `get_weather_by_position` 内部管理
3. **月相精度**：来自 `get_nightly_forecast` 的 astropy 计算，不依赖网络
4. **无用户偏好**：当前不区分观测目的（深空摄影 vs 目视 vs 行星观测），所有地点用统一算法打分

## 未来扩展方向

参见 `docs/ROADMAP.md` Priority 2：

- 支持观测偏好（astrophotography / casual viewing / bright-object）
- `get_best_targets_for_telescope`：按望远镜口径推荐目标
- 更强的排名策略：多目标优化、用户历史偏好
- 地点聚类去重（避免返回过于接近的多个候选）
