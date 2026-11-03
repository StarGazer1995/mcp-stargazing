# Stargazing Workspace 技术地图

## 三仓依赖关系

```text
stargazing-core --------------------------> mcp-stargazing
       |                                         ^
       +----> stargazing-place-finder -----------+
```

三仓通过真实 wheel 的 baseline/candidate CI 验证兼容性。依赖发布仍以 PyPI 为权威来源。

## 责任边界

| 仓库 | 主要职责 | 不应承担 |
|---|---|---|
| `stargazing-core` | 可复用天文与光学计算、共享模型、目标匹配、拍摄与天气空间数据原语 | MCP 协议、用户对话、地点 provider 编排 |
| `stargazing-place-finder` | 地点候选召回、光污染、地形、路网、POI 与静态地点画像 | agent-facing 响应、跨夜动态决策 |
| `mcp-stargazing` | MCP 契约、应用编排、动态天气与天空条件组合、降级语义、推荐解释 | 复制下层 GIS 或光学算法、暴露部署路径 |

判断新能力归属时使用以下规则：

1. 无 MCP 也有复用价值的确定性计算优先进入 core；
2. 围绕“这个地点本身怎么样”的空间判断进入 place-finder；
3. 围绕“这次用户什么时候去、去哪、做什么”的组合决策进入 MCP 应用层；
4. provider 请求与领域评分分离，provider 返回标准化信号，评分器消费信号；
5. 公共工具 wrapper 不作为跨模块长期业务接口。

## 当前主调用链

天气聚合通过同一个 Open-Meteo adapter 提供普通天气与可选大气状态：复用天气响应的
能见度/边界层数据，只额外取 CAMS global 空气数据，按有效时间连接进当前/小时
`atmosphere` 字段。独立来源错误记录在 `atmosphere_sources`，不让空气失败吞掉天气。
本次不新增 MCP 入口或改变规划权重，契约边界见 [扩展审查](weather-atmosphere-contract.md)。

```text
third-party agent
  -> FastMCP tools/list + tools/call
    -> src/functions/*/impl.py
      -> src/celestial.py / weather service / src/placefinder.py
        -> stargazing-core / stargazing-place-finder / external providers
```

组合规划已增加独立 application service：

```text
get_best_stargazing_plan / get_multiday_stargazing_plan
  -> src/services/planning.py
    -> injected place / weather / forecast / night-window capabilities
      -> domain calculations / providers / caches
```

service 不依赖 FastMCP、响应 envelope 或工具注册，可以通过普通异步 callable 独立测试。
其中多晚规划已直接复用 service 的单晚规划，不再调用另一个公共 planning wrapper。
地点分析、坐标天气和夜间目标已经各自提供无 MCP envelope 的内部 capability；公共
工具与 planning adapter 复用同一能力。源代码契约测试禁止 planning 重新调用 `.fn`。

## 演进目标结构

```text
MCP public contract
  -> planning application service
    -> place candidate service
    -> weather/sky window service
    -> target/equipment service
    -> ranking + explanation service
      -> core / SPF / external adapters
```

同一份结构化 factor 同时驱动分数和解释，避免排序逻辑与推荐文案分叉。

## 当前技术债热点

### 1. 候选召回与动态粗排（已实现）

`get_best_stargazing_plan` 使用有界扩大的静态召回池，先查询低成本天气并进行粗排，
再对强候选进行天空与窗口计算，最后按 `candidate_limit` 截断。已有排名反转回归。

后续：仅根据同基准实测调整召回与精算成本，不把旧的过早截断问题重复列为待办。

### 2. 排名与解释共享 factor 模型（已实现）

当前 `score_breakdown` 已暴露地点、天气、热门度与便利性贡献。规划从 SPF 获取
关闭热门度偏好计权的地点基础分，MCP 独立应用用户偏好，避免两层重复加减分。
单独调用 `analysis_area` 时仍由 SPF 按偏好排序。

后续可继续细化子因子的解释追溯，并校准相关启发式权重。

### 3. 兼容入口保留部署参数

`db_config_path` 是服务器部署信息，`weather_provider` 更适合高级诊断或服务端策略，均不应继续扩散到新的主规划入口。

主入口 `plan_stargazing_session` 已使用地点意图、时间、设备和偏好，不暴露部署路径。
既有 bbox-first 入口按迁移约定保留参数；新能力不继续扩散这些部署细节。

### 4. 连续窗口与目标一致性（部分已实现）

当前 best window 已从近时段预报中合并为连续暗夜窗口；`score_breakdown.factor_contributions`
与推荐理由共享实际排名因子；SPF 提供中性地点分与 popularity 信号，MCP 负责规划偏好计权。

主规划对设备 shortlist 逐个调用 core 公共排程，在所选天气窗口核对完整高度曲线及
现有月落延迟策略。无时段者排除，缺失曲线保留为明确未知参考，证据列出独立模型时段。
通用目标、逐时月距、跟踪/地形限制与联合曝光分配尚未全部验证，不能用整夜 peak
或设备分数代替这些检查；当前窗口选择和地点分数不因本次目标过滤而改动。

### 5. 长任务协议与恢复（已实现）

`services/tasks.py` 管理任务状态，`services/area_tasks.py` 管理有界线程执行与实际资源占用，
`functions/places/tasks_impl.py` 提供四个公共任务工具。取消与超时后的迟到结果在发布前
被拒绝；缓存发布版本与查询标识分离，分页不能悄悄读到被替换的数据。当前仅进程内恢复，
断线/重启场景及跨进程策略见 `task-lifecycle.md`。

后台任务协议已启用并完成断线、重启、分页和第三方客户端验收；跨进程持久恢复
仍不是当前承诺，普通同步规划也不会被伪装成长任务。

### 6. 进程内缓存缺少数据新鲜度模型

`analysis_area` 使用进程内 TTL 缓存；天气、光污染、地点画像的更新时间与失效原因尚未形成统一 evidence 结构。

目标：区分计算缓存、静态数据版本和动态 provider 时效。

## 变更影响表

| 变更 | 主要仓库 | 必须同步检查 |
|---|---|---|
| 新增天文/光学计算 | core | 两个 consumer 的 wheel CI、公共导出 |
| 新增地点画像字段 | SPF | MCP bridge/schema、缓存 key、planning 消费 |
| 修改主规划契约 | MCP | README、ROADMAP、Agent Contract、协议与快照测试 |
| 修改 bridge | MCP + SPF | `bridge-boundary.md`、跨仓 wheel CI |
| 修改长期任务语义 | MCP | transport 测试、资源生命周期、错误与恢复语义 |
| 修改排名 factor | MCP 或 SPF | golden scenarios、解释一致性、排名反转测试 |

## 权威文档

- 公共工具：`README.md`
- 第三方 agent 目标契约：`docs/agent-contract.md`
- 实施顺序：`docs/workspace-action-checklist.md`
- 能力路线：`docs/ROADMAP.md`
- Bridge 边界：`docs/bridge-boundary.md`
- 分页与缓存：`docs/analysis-area-semantics.md`
- 跨仓 CI：`docs/dependency-chain-ci.md`
