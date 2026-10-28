# 外部 AI 的规划结果判读指南

适用于 `plan_stargazing_session`、兼容规划入口，以及天气和目标支撑工具。
关键约束同时写入标准 MCP description；调用方通过 `tools/list` 即可读取。
接入具体服务时应重新发现工具并核对部署版本，不能仅凭仓库文档认定服务已更新。
响应 `_meta.version` 是 envelope 版本，不是部署包版本。

## 请求表达的是区域选址还是固定点

`location` 只能选择 `place_name`、`center`、`bounds` 之一。
只传 schema 中已定义的字段；不能自行添加未实现的 `constraints` 对象。
`center + radius_km` 会构造近似搜索框；它不是锁定中心点，也不提供严格圆形距离过滤。
`place_name` 的解析结果也可能是行政区域中心。必须检查 `resolved_location` 和最终
`decision.location` 的坐标/名称，再描述实际推荐的地点；不能把周边瀑布称为指定的天池点位。

`avoid_popular_spots` 和 `prefer_quiet_at_night` 默认关闭，需要用户要求时显式开启。
`static_popularity_risk_score`、`night_quiet_likelihood_score` 是启发式分数，
不是现场测量、分贝数、人流统计或经校准的概率。分数低不能直接证明现场吵闹。

标准 `tools/call` 的参数形状如下，`request` 必须是对象，不能是序列化后的字符串：

```json
{
  "name": "plan_stargazing_session",
  "arguments": {
    "request": {
      "location": {"center": {"lat": 30.485, "lon": 119.468}, "radius_km": 15},
      "start_date": "2026-11-06",
      "time_zone": "Asia/Shanghai",
      "nights": 3,
      "observation_style": "deep_sky",
      "equipment": {"preset": "hope_d60_asi2600mc_air"}
    }
  }
}
```

日期只是格式示例，不是对该日天气的承诺。不同 CLI 的参数解析不同；不能假设
`--request '<JSON>'` 会自动转成嵌套对象。现有
[`agent_planning_demo.py`](../examples/agent_planning_demo.py) 的 `--request` 接收 JSON 文件路径，
客户端负责把其内容放入 MCP 参数的 `request` 对象。

## 成功执行不等于获得可出行方案

首先检查 envelope 的 `error` 与 `_meta.status`，再检查业务结果：

| 字段或情况 | 可以得出的结论 | 不能得出的结论 |
|---|---|---|
| `_meta.status="success"` | 这次工具执行成功 | 天气晴、资料完整或一定适合出发 |
| `decision=null` | 没有选出首选方案，应读取原因和后续动作 | 已经验证所有地点都不能观测 |
| `observation_window=null` | 没有建立可用窗口，应读取不确定性 | 整晚都可拍，或可直接用民用暗夜时长代替 |
| `recommendation_score` | 同一查询/偏好下的相对排序分 | 成功概率、绝对出行阈值或不同偏好的可比精度 |
| 夜晚分数相同 | 当前可用因素给出并列结果，可能含回退值 | 各晚天气一定相同，或一定存在复制错误 |

必须共同读取 `evidence`、`uncertainties`、`missing_inputs`、`would_change_if`、`next_actions`。
兼容入口对应读取 `summary.warnings`、各夜的 `error/warnings` 和候选 `notes`。

- `nightly_weather_unavailable`：缺少所选夜晚的可用逐小时天气；排序可能含中性回退。
- `nightly_weather_partial`：小时数据未完整、连续覆盖观测区间。
- `no_usable_observation_window`：已有预报中未找到满足云量、降水、风速条件的时段。
- `long_range_forecast`：七天及更远的预报被保守标记，临近出发需要重查。

前两种缺失情况不能补成“晴天”。以上诊断可能出现在 notes、结构化 uncertainties 的
code 或 message 中；保留原始诊断，不根据响应成功标记将其丢弃。

## 天气必须对应地点和实际夜间时段

原子天气工具返回的 `summary.current` 是当前条件，`summary.daily` 是日级资料，
`summary.hourly` 才是逐时预报。夜晚跨过本地午夜，不能只按起始日字符串筛选。
不能把当前天气、日均云量、白天能见度或单个 21:00 时次解释为整晚天气。
主规划的 `start_date` 指夜晚开始的本地日期；原子天文/目标工具的 `time` 则是具体时刻。
裸日期会解析成当地 00:00，可能落在前一晚，不能自动当成该日傍晚。

规划结果的 `weather_summary` 使用观测区间的逐小时预报统计，名称相似但不等于
原子天气的 `summary.current`。天气 evidence 的 facts 记录 provider、统计起止、
首末预报时次、时次数和云量聚合方式；当前实现逐小时取总云量/各层云量的最大值，
再在时段内求均值。优先使用目标区间内有效样本更多的单一数据源，样本数相同时
Open-Meteo 优先；这仍不保证完整覆盖，应检查覆盖诊断。
不要仅根据 `Clear` 这样的文字猜测来源。

`observation_window` 的云量、降水和风速是窗口起始样本，`quality_score` 是窗口内
综合启发式均分，不等于整晚平均云量或晴天概率。因此它们与整段 `weather_summary`
数值不同不一定是矛盾。窗口和分数都是筛选结果，不是实际曝光质量保证。

Open-Meteo 请求最长十六天，但不同 provider、模型、字段的实际覆盖可能不同；
应以时间戳和非空数据为准。缺失值仍是未知，不能用另一时刻的能见度补齐。
空间模型超出可用时次时会降级，不能把最后一个预报时次延长到目标日期。
预报描述的是未来预测，不是已经实测到的未来天气。

## 暗夜、目标高度与拍摄时长不能混用

`night_window` 是民用暗夜（太阳高度低于 −6°），不是天文黑夜（−18°）。
`night_window.duration_hours` 是该时间区间长度，不能直接称为保证的深空曝光时长。
`best_observation_window` / `decision.observation_window` 还受小时预报约束，
也不代替天文暮光、地形遮挡、道路/场地开放和现场天气核实。

| 目标来源/字段 | 实际含义 |
|---|---|
| `get_telescope_targets.targets[].altitude` | 民用暮光时的高度，单位度，不是调用时刻高度 |
| 同一目标的 `azimuth` / `dawn_altitude` | 分别为民用夜间中点方位角 / 黎明高度 |
| `altitude_curve[].time` / `alt` | UTC Unix 秒 / 该采样时刻高度（度） |
| 望远镜目标的 `transit_time` / `transit_alt` | 夜间采样曲线的最高点时刻（UTC Unix 秒）/ 高度（度），不是另行求解的精确子午线通过事件 |
| `rise_time` / `set_time` | 窗口内地平线穿越时刻；null 不等于永不升起/落下 |
| `get_nightly_forecast.deep_sky[].altitude` | 请求时刻的高度 |
| 同一通用预报的历史 `transit_alt` | 评分时刻高度的近似值，不是独立求得的真实中天高度 |

具体钟点的高度应读取曲线或调用 `get_celestial_pos`，不能只看暮光时高度就判断“不对季”。
通用 `deep_sky.score` 越低越靠前；望远镜 `suitability_score` 越高越靠前。
主规划紧凑目标中的 `score` 随来源继承这两种含义，不应跨来源比较。
设备 preset 已使用时，优先消费主规划返回的设备匹配目标；需要精确排程再调用拍摄计划工具。
缺失星等/表面亮度表示光度资料未知，不等于目标不可见，也不能虚构满额亮度优势。

拍摄排程使用民用暗夜与目标高度条件，不验证未来天气、现场开放或实际完成的积分时间。
主规划仍是同步调用；扩大夜晚/候选范围可能超过客户端默认超时。超时不能单独证明
返回数据错误，也不能在没有任务编号时假定后台规划任务已创建。
