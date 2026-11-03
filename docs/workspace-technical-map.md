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

### 1. 候选召回与动态筛选已实现，后续按实测优化

规划先扩大静态地点召回，使用点天气和区域云量筛选，再对有限候选执行昂贵的目标与
夜间窗口计算。回归测试保护“静态排名较低但当晚天气最佳”的地点进入推荐。

后续：用部署版本与固定请求的阶段计时确定瓶颈，再调整调用复用、并发和超时。

### 2. 排名与解释已共享 factor，启发式仍需实况校准

当前 `score_breakdown` 已暴露地点、天气、热门度与便利性贡献。规划从 SPF 获取
关闭热门度偏好计权的地点基础分，MCP 独立应用用户偏好，避免两层重复加减分。
单独调用 `analysis_area` 时仍由 SPF 按偏好排序。

后续可继续细化子因子的解释追溯，并校准相关启发式权重。

### 3. 公共参数包含基础设施细节

`db_config_path` 是服务器部署信息，`weather_provider` 更适合高级诊断或服务端策略，均不应继续扩散到新的主规划入口。

目标：公共输入表达地理、时间、目标、设备和用户约束；部署配置留在服务端。

### 4. 连续观测窗口已实现，目标与排程仍需联合验收

当前 best window 已从近时段预报中合并为连续暗夜窗口；`score_breakdown.factor_contributions`
与推荐理由共享实际排名因子；SPF 提供中性地点分与 popularity 信号，MCP 负责规划偏好计权。

深空摄影窗口还受版本化 `deep-sky-v1` 天文黑夜与天气门槛约束。
后续：联合检查具体目标高度、月距、设备要求和拍摄排程，明确目标实际可拍的连续时段。

### 5. 后台任务已交付，目前仅支持进程内状态

`services/tasks.py` 管理任务状态，`services/area_tasks.py` 管理有界线程执行与实际资源占用，
`functions/places/tasks_impl.py` 提供四个公共任务工具。取消与超时后的迟到结果在发布前
被拒绝；缓存发布版本与查询标识分离，分页不能悄悄读到被替换的数据。当前仅进程内恢复，
断线/重启场景及跨进程策略见 `task-lifecycle.md`。

后续：只有出现多实例或跨重启恢复需求时再引入共享存储，当前重启后明确要求重交。

### 6. 进程内缓存缺少数据新鲜度模型

`analysis_area` 使用进程内 TTL 缓存；天气、光污染、地点画像的更新时间与失效原因尚未形成统一 evidence 结构。

目标：区分计算缓存、静态数据版本和动态 provider 时效。

### 7. 真实预报验证与大气解释

`evaluations/forecast_archive.py` 保存查询时的逐 provider 预报，独立记录取回起止时间，
以严格地点、坐标、有效时刻和测量口径配对独立实况。上游没有起报时间时保持未知，
提前量明确以完成取回时间为基准。实况来源的独立性仍需人工审查，字段标签不能证明准确。

后续：接入有来源与许可说明的独立观测；按观测窗口汇总大气 evidence 和风险说明，
不在未经验证时用新大气指标改变规划评分。

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
