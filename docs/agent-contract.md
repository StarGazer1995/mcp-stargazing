# 第三方 Agent 契约方向

## 状态

本文定义 `mcp-stargazing` 面向第三方 AI agent 的目标契约与演进约束。
它描述的是 **1.0 方向**，不是对尚未实现字段的承诺。当前已经注册的工具、参数和返回值仍以
`tools/list`、`get_tool_catalog` 和 `README.md` 为准。

## 北极星目标

一个不了解仓库内部结构的第三方 agent 应当能够：

1. 从工具描述中选择正确入口；
2. 用用户意图而不是部署细节表达请求；
3. 在一次主规划调用后得到首选方案、备选方案和可核查依据；
4. 区分事实、启发式推断、缺失数据和降级结果；
5. 在部分 provider 失败时继续工作，并知道下一步可以做什么；
6. 在服务升级后继续稳定消费未弃用的字段。

## 工具分层

### 主决策入口

当前主入口是：

- `get_best_stargazing_plan`
- `get_multiday_stargazing_plan`

目标形态是在 1.0 前形成一个更 agent-native 的统一观测规划入口。主入口概念名确定为
`plan_stargazing_session`；在输入、输出、迁移评审和黑盒 agent 验收通过前，不注册这个
新工具，避免制造第二套尚未成熟的重叠契约。

主入口负责回答：

- 哪个夜晚更合适；
- 哪个地点更合适；
- 适合看什么或拍什么；
- 可执行的连续观测窗口是什么；
- 为什么第一名优于备选项；
- 哪些变化可能推翻当前推荐。

### 支撑工具

支撑工具提供地点、天气、天体和设备维度的深入查询。它们可以被 agent 单独调用，也可以由应用服务组合：

- 地点：`analysis_area`、`light_pollution_map`
- 天空：`get_nightly_forecast`、天体位置与升落工具
- 天气：`get_weather_by_name`、`get_weather_by_position`
- 设备：`get_telescope_targets`、`get_shooting_plan`

### 诊断与发现工具

- `get_tool_catalog` 用于程序化检查工具元数据。
- 低层工具不能依赖调用方理解仓库内部模块、provider 实现或服务器文件系统。

## 公共参数边界

第三方 agent 应表达用户意图，而不是服务器部署方式。

### 应当成为公共输入

- 地理意图：地点文本、中心点与半径、或精确 bbox；
- 时间意图：指定时刻、日期范围、连续夜晚数量；
- 观测目标：深空摄影、目视、行星、入门等；
- 设备：稳定 preset 或显式光学参数；
- 用户约束：候选数量、连续晴朗时长、道路可达性、热门度偏好；
- 结果预算：返回多少候选、多少目标、是否需要详细证据。

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

主规划结果最终应稳定表达以下语义。字段名需经过实现评审后再冻结：

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

第 1、2 步已经完成：`AgentPlanningRequest` 支持地点文本、中心点加
半径和精确 bbox，`AgentPlanningResult` 提供 decision、alternatives、精确评分分解、证据、
不确定性、关键缺失输入、排名反转条件和下一步动作。Seestar S50、HOPE D60 +
ASI2600MC Air 和 custom optics 会先归一化，再对首选 session 做设备目标匹配；provider 和
数据库路径不进入请求模型。10 个冻结 golden scenarios 全部通过，Codex CLI 与 Claude Code
在代表性 HOPE D60 + ASI2600MC Air 场景中均首次选择正确工具、首次实际调用成功并返回正确
答案。当前仍保持 16 个公开工具；注册 `plan_stargazing_session` 留给下一项独立变更。

## 版本与弃用策略

1. 1.0 前允许经过文档和迁移说明的 breaking change。
2. 1.0 后工具重命名、必填参数增加、枚举删除和字段语义变化均视为 breaking change。
3. 新契约替代旧契约时，旧入口至少经历一个有文档的弃用周期。
4. 增量字段必须有稳定默认值；缺失与 `null` 的语义必须写清楚。
5. `tools/list`、`get_tool_catalog`、README 和契约测试必须同步。

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
