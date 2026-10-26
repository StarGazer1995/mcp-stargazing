# 区域分析任务生命周期

## 当前交付边界：P5.2

`AnalysisTaskRegistry` 管理元数据，`AreaTaskService` 管理有界后台执行与结果发布。
四个 MCP 工具提供提交、轮询、取消和分页，响应通过 `_meta.task_id` 关联任务。
同步 `analysis_area` 继续可用，两条路径复用同一计算、分页与缓存语义。
目前通过实际 MCP SDK 验证工具调用链；独立进程断线、重启以及第三方 AI 的选工具验收
仍属于后续工作，不能把状态机单测当成这些验收已完成。

| 工具 | 输入与行为 |
|---|---|
| `submit_area_analysis` | `request.bounds` 与搜索偏好；返回任务和规范化请求，`max_locations` 限 1–100 |
| `get_area_analysis_task` | `task_id`；返回状态、时间、真实已知进度与失败信息 |
| `cancel_area_analysis_task` | `task_id`；记录幂等逻辑取消 |
| `get_area_analysis_result` | `task_id`、`page`、`page_size`；只读取成功任务原有的分页结果 |

执行失败时，状态查询本身仍是成功响应，调用方须检查 `data.state` 与 `data.failure`。
使用示例见 `examples/background_area_demo.py`。

## 状态与转换

| 状态 | 含义 | 后续转换 |
|---|---|---|
| `queued` | 已登记，等待 worker 领取 | `running`、`cancelled`、`timed_out` |
| `running` | 一个 worker 已领取 | `succeeded`、`failed`、`cancelled`、`timed_out` |
| `succeeded` | worker 已确认结果发布成功 | `expired` |
| `failed` | worker 报告执行失败 | `expired` |
| `cancelled` | 已记录逻辑取消 | `expired` |
| `timed_out` | 从提交时刻计算的截止时间已到，含排队耗时 | `expired` |
| `expired` | 终态元数据保留期已到 | 容量不足时可回收 |

时间均为 UTC。时钟可注入，测试无需真实等待；生产时钟使用 `datetime.now(UTC)`。
截止时间与过期在 `get`、`submit`、`start`、完成或取消操作时检查，没有后台定时器。
超时的 `finished_at` 为实际截止时刻，保留期也从该时刻起算，晚轮询不会延长任务寿命。

`start` 原子地领取排队任务，重复领取返回 `invalid_transition`，避免重复 worker 执行。
成功和失败的同类完成通知可重试，第一次记录的时间与失败信息保持不变。
取消可重复请求；对已有终态取消时返回原状态。取消、超时或过期后，迟到的成功/失败
通知均被拒绝，不能覆盖原终态。

进度只表达真实已知信息：排队为 `0`，执行中为 `null`（进度未知），成功确认为 `1`。
失败、取消与超时保留之前的进度，不因为“处理结束”就写成 100%。

## 任务标识与资源标识

- `resource_id` 沿用 `analysis_area` 的非分页搜索参数标识，由能力接入层计算并传入 registry。
  registry 不重新哈希参数，也不接收页码或每页数量。
- `task_id` 是一次执行的随机标识，包含 registry 实例标记。相同查询只在排队或执行中
  复用同一个 `task_id`；成功、失败、取消或超时后重交会生成新任务，`resource_id` 可相同。
- 一个查询标识不等于一份永久不可变的数据版本；重算同一查询可能得到不同地点数据。
- 成功任务保存 `result_revision`，绑定该次缓存发布。同键被同步分析或后续任务重新写入时，
  旧任务不能读取新版本；每次取页同时校验查询标识与发布版本。
- 任务元数据与 `ANALYSIS_CACHE` 各自保留、各自过期。任务成功不保证地点缓存仍在，
  后续结果接口必须实际检查缓存，缺失时引导重交原始查询，不能伪装成空结果或偷偷重算。
- 任务没有持久化。重启后旧编号返回 `TASK_RUNTIME_CHANGED`，调用方需重交规范化请求；
  本实例未找到或已回收的编号返回 `TASK_NOT_FOUND`；格式错误返回 `CONFIGURATION_ERROR`。

## 并发与容量

登记、领取、转换与轮询由同一个锁保护。相同资源的并发提交只产生一个活动任务。
返回对象和传入失败信息均复制，调用方不能通过修改快照改变登记状态。

默认最多保留 128 条记录，截止时间为提交后 600 秒，终态保留 3600 秒；这些是可注入的
服务端策略，不扩展公共输入。记录容量包括活动任务和未过期终态，容量不足时只回收过期
记录；仍满则返回 `TASK_CAPACITY_EXCEEDED`，不淘汰活动任务或仍承诺保留的记录。

执行器默认 2 个 worker、8 个排队位置。逻辑取消或超时不会中断已经运行的同步 provider
调用；它实际结束前仍占预算，`execution_pending` 表达这一差异。同一资源尚在收尾时，
重交返回容量错误，不能无限启动替代工作。SPF 使用进程共享实例，计算入口另有锁保护
配置与分析的完整区间；worker 数不代表 SPF 能并行计算多个区域。

成功发布与状态提交在 registry 同一把锁内协调；取消或超时已生效的 worker 不再写缓存。
服务退出时拒绝提交、取消排队任务并丢弃运行任务的迟到结果，不强杀线程。

部署策略由服务端环境变量配置，均不进入工具参数：`STARGAZING_TASK_MAX_RECORDS`、
`STARGAZING_TASK_TIMEOUT_SECONDS`、`STARGAZING_TASK_RETENTION_SECONDS`、
`STARGAZING_TASK_WORKERS`、`STARGAZING_TASK_QUEUE_CAPACITY`。
仅支持单进程 runtime；多副本需固定路由到原实例，跨进程恢复需要共享存储。

## 错误与恢复

| 错误码 | 下一步 |
|---|---|
| `TASK_NOT_FOUND` | 核对编号；记录已回收时重交原始请求 |
| `TASK_RUNTIME_CHANGED` | 重交请求，不继续轮询旧编号 |
| `TASK_CAPACITY_EXCEEDED` | 稍后重试；取消任务仍可能在实际收尾 |
| `TASK_NOT_READY` | 继续轮询状态，暂不取结果 |
| `TASK_UNAVAILABLE` | 检查终态与失败详情，实际执行结束后决定是否重交 |
| `TASK_RESULT_EXPIRED` | 缓存缺失、被替换或任务已过期；重交规范化请求 |

不会把缓存失效伪装成空结果，不会在取页时偷偷重算。客户端断开也不自动取消任务。

P5.1 测试见 `tests/test_task_lifecycle.py`：覆盖时钟边界、迟到通知、幂等终态、并发去重与
领取、容量回收、重启行为、失败信息隔离和 JSON 序列化。
P5.2 测试见 `tests/test_area_tasks.py` 与 `tests/test_area_task_tools.py`，覆盖实际线程预算、
排队取消、迟到发布、版本绑定、缓存独立过期、SDK 调用链及 shutdown 清理。
