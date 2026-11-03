# 天气聚合的大气状态契约扩展

## 变更与兼容性审查

2026-11-01，扩展天气聚合以提供空气组成、能见度和大气扩散上下文。
继续使用 `get_weather_by_name` 和 `get_weather_by_position`，参数、响应 envelope、
旧字段的单位与语义保持不变。公开工具集合保持 21 个，不涉及入口的删除或弃用。

本次显式批准的兼容增量：

| 模型 | 新增可选字段 | 缺失语义 |
|---|---|---|
| `CurrentWeather` | `atmosphere` | 默认 `null`，没有可用的大气状态 |
| `HourlyForecastItem` | `atmosphere` | 默认 `null`，该有效时间没有可用大气数据 |
| `NormalizedWeatherData` | `atmosphere_sources` | 默认 `{}`，该天气 provider 不提供大气数据 |
| `WeatherSummary` | `atmosphere_sources` | 默认 `{}`，摘要没有大气来源 |

`tests/public_schema_baseline.json` 和 `tests/public_contract_v1.json` 保持不动。
新增字段及其全部新类型单独记录在 `tests/weather_atmosphere_contract.json`。
v1 门禁先精确核对这份扩展，只投影去除上表中的可选字段与明确记录的新定义，随后
继续精确比较全部旧 schema。新增必填字段、修改旧字段或任意未审查变化仍会失败。
机器可读审查记录见 `contract-policy.json` 的 `compatible_extensions`。

## 数据位置与解释

- `data.summary.current.atmosphere`：最近当前天气所在整点的大气模型状态；读取其自己的
  `time`，不要把父层 `observation_time` 当作大气观测时间。
- `data.summary.hourly[*].atmosphere`：按有效时间精确匹配该天气小时的模型状态。
- `data.summary.atmosphere_sources`：来源、分辨率、有效时间范围、单位、警告和独立错误。
- `data.providers[provider].data`：同样的逐 provider 字段，保留来源追溯能力。

`AtmosphericState` 提供 `boundary_layer_height_m`、`visibility_km`、`pm2_5_ug_m3`、
`pm10_ug_m3`、`no2_ug_m3`、`o3_ug_m3`、`so2_ug_m3`、`co_ug_m3`、`aod_550nm` 和
`dust_ug_m3`。CO 也以 μg/m³ 表示；AOD 无量纲。
`field_sources` 将每个非空值指向摘要或 provider 的 `atmosphere_sources` 键。

所有状态均标为 `data_kind=model_estimate`，`temporal_role` 区分过去模型估计、当前
模型估计与未来预报。`time` 统一为带 UTC offset 的 ISO 字符串；来源 `retrieved_at`
是请求开始时间，`model_run_time=null` 表示上游未提供起报时间。不得将查询时间视为
观测/起报时间。DST 重复或不存在的本地小时不会猜测转换，大气状态保持未知。

## 取数与降级

Open-Meteo adapter 在现有天气请求中增加小时能见度与边界层高度，复用该响应；仅额外
请求一次 CAMS global 空气质量接口，最长三次瞬时网络错误重试。天气请求仍保留原有
预报范围，空气请求为五个 UTC 日历日。CAMS 原始全球网格约 45 km、原始时间步长
3 小时；小时输出可能插值，不能当作道路尺度的小时观测。

空气与天气按时间戳连接，不按数组位置，不取最近时刻，不外推空气范围。空值、无穷值、
负污染物值、错误单位和不完整数组均保持未知；合法零值保留。来源覆盖起止是返回
有效时间范围，不保证区间内每个字段完整。单个时刻以实际 `null` 为准。

空气失败只设置大气来源的错误状态，不把整个天气 provider 变成失败。`provider=all`
包含 Open-Meteo 时可获得此扩展；显式 `provider=qweather/wttr` 不偷偷额外请求
Open-Meteo，这些 provider 暂返回 `atmosphere=null` 与空来源。

当前天气的聚合将整个 `atmosphere` 作为一个带自身时间的状态保留，不按字段拼接
不同时刻的空气数据。小时摘要沿用原有主 provider 的天气序列。

## 能力边界

AOD 是整层气溶胶消光，不能直接等同地面 PM、水平能见度、视宁度或透明度倍数。
边界层高度相对当地模型地面，不能作为硬性的污染层顶，或用另一地点的边界层高度
证明山顶位于清洁自由大气。风向与浓度走势不能单独归因具体城市、交通或二次生成。
不计算 AQI/健康类别，不改变规划器评分。主规划器在选定窗口后，将模型指标汇总为
独立描述与不确定性，新增指标不参与排序或窗口准入。范围和缺失语义见
[窗口大气证据](planning-atmosphere-evidence.md)。

## 验证

`tests/test_atmosphere.py` 覆盖两个现有入口、来源过滤、时间对齐、独立失败、预报范围、
单位与非法值、DST 和实际 MCP 客户端调用。`tests/test_weather_atmosphere_contract.py`
保护新增契约和旧字段投影。SDK/HTTP 工具集合恢复为原有 21 个入口。
