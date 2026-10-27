# 第三方 Agent 演进清单

## 使用方式

本清单把 `docs/agent-contract.md` 的目标拆成可验收阶段。只有代码、文档、测试和黑盒场景同时满足时，任务才算完成。

## P0：Contract Baseline

- [x] 明确第三方 agent 是优先调用方；
- [x] 写明主入口、支撑工具和诊断工具的层级；
- [x] 写明用户意图参数与部署参数的边界；
- [x] 建立三仓技术地图和能力归属规则；
- [x] 重新划分 Roadmap，把已完成能力移出未来主线；
- [x] 增加文档引用与运行依赖版本的防漂移测试；
- [x] 合并 multi-night / night-window 变更；发版仍由独立发布指令触发；
- [x] 对原有 16 个工具形成公共参数审计表，并在注册主入口后扩展为 17 个；
- [x] 为每个工具补充稳定的使用/误用边界、前置输入、返回内容和后续工具说明；
- [x] 保存 1.0 前公共 schema baseline，并通过真实 `tools/list` 与详细模型检查保护既有接口。

验收：README、工具目录、依赖下限和 docs 引用由测试保护；第三方目标契约成为新增 agent-facing 能力的评审依据。

路由说明已经进入全部 21 个工具的标准 MCP description。SDK 和真实 HTTP 发现测试
验证说明完整、后续工具确实已注册，并可从既有 catalog 字段读取；历史 schema 基线保持不变。

## P1：应用服务边界

- [x] 从 planning 中抽出独立 application service；
- [x] planning 不再以其他 MCP wrapper 的 `.fn` 作为长期内部接口；
- [x] 保持现有工具响应兼容；
- [x] 建立 service 层成功、降级和错误测试；
- [x] 明确主规划入口是演进现有工具还是新增统一入口；
- [x] 为任何新入口写迁移与弃用计划。

当前状态：单晚与多晚编排、校验、排序和解释已进入 `src/services/planning.py`；
多晚规划直接调用 service 的单晚能力。地点、天气与夜间目标均提供无 MCP envelope
的内部 capability，planning 的生产代码不再调用任何公共工具 `.fn`。契约测试会阻止
该耦合重新出现。

主入口决策：未来新增 `plan_stargazing_session`，不把 agent-native 参数继续堆入现有
bbox-first 工具。新入口只有在应用模型、golden scenarios 和多客户端黑盒验收通过后才
注册；旧 planning 工具至少保留一个有文档的迁移周期。

验收：公共工具签名变化不会迫使内部组合逻辑同步改写；服务层可以在没有 MCP transport 的情况下测试。

## P2：Agent-native 输入与输出

- [x] 支持地点文本或提供明确的地点解析前置工具；
- [x] 支持设备 preset，并允许高级调用方覆盖光学参数；
- [x] 新主入口不暴露 `db_config_path`；
- [x] provider 选择默认由服务端策略管理；
- [x] 返回首选、备选和结构化比较；
- [x] 增加 `score_breakdown`；
- [x] 增加 evidence、uncertainty 和 missing-input 语义；
- [x] 增加 `would_change_if` 与 `next_actions`；
- [x] 默认值全部回显并有契约测试。

当前状态：P2 已在 application contract 中完成。`AgentPlanningRequest` 与
`AgentPlanningResult` 可直接做 transport-free 测试；Seestar S50、HOPE D60 +
ASI2600MC Air 和 custom optics 会驱动首选 session 的设备目标匹配。P4 gate 通过后，
`plan_stargazing_session` 已作为第 17 个公开工具注册；旧的 bbox-first planning 工具继续兼容。

验收：第三方 agent 不需要理解仓库、provider 或服务器文件系统即可完成一次规划。

## P3：决策质量

- [x] 扩大静态候选召回，避免天气查询前按最终数量截断；
- [x] 接入低成本空间天气粗排；
- [x] 对 Top N 执行精细目标与设备计算；
- [x] 复用 `stargazing-core` 空间云量网格做区域级比较，并保留模型失败降级；
- [x] 从最佳单小时升级为连续观测窗口；
- [x] 同一 factor 同时驱动排名和解释；
- [x] 消除 SPF 与 MCP 对同一 popularity 信号的重复计权：规划请求中性地点分，MCP 单独应用偏好；
- [x] 建立第一名与第二名的排名反转测试。

验收：构造“静态第四名但天气最佳”的场景时，该地点能够进入最终候选并在合理条件下成为第一名。

## P4：Agent 评测

- [x] 建立至少 10 个真实 planning golden scenarios；
- [x] 覆盖深空、目视、行星、入门和设备 preset；
- [x] 覆盖空候选、provider 部分失败、无夜晚窗口和历史时间；
- [x] 评测工具选择正确率；
- [x] 评测首次调用成功率；
- [x] 评测 ranking correctness 和 explanation faithfulness；
- [x] 评测降级后是否仍可行动；
- [x] 至少使用两个不同第三方 agent 客户端做黑盒验收。

结果：可执行 golden scenarios 为 10/10；Codex CLI 与 Claude Code 在同一 HOPE D60 +
ASI2600MC Air 代表性场景上均为工具选择 2/2、首次实际调用成功 2/2、答案正确 2/2。黑盒
结论只代表该抽样场景，不等同于两个客户端各自跑完全部 10 题。证据见
`evaluations/reports/2026-10-25-two-client-smoke.md`。

生产注册：`plan_stargazing_session` 已通过独立变更进入生产 MCP surface；README、
`tools/list`、`get_tool_catalog`、契约测试和 evaluation adapter 已同步。P3 决策质量清单
已完成，下一阶段为 P5 长任务；不在没有状态机的情况下提前暴露形式化 `task_id`。

验收：发布前可以明确判断新变更改善了决策，还是只增加了字段与复杂度。

## P5：长任务与资源

- [x] 定义 task 状态机（P5.1 registry，P5.2 已绑定后台执行）；
- [x] 定义 `task_id`、`resource_id` 与查询参数的关系，并绑定能力接入层；
- [x] P5.2 接入后台执行、状态轮询、取消和分页取结果，运行进度未知时明确返回 null；
- [x] P5.3 完成断线重连、真实进程重启及分析中进程崩溃场景的协议恢复验收；
- [x] P5.4 完成第三方 AI 的只读任务工具选择与恢复判断验收（两个客户端各 10/10）；
- [x] P5.5 补齐第三方 AI 主动提交、分页、取消与活动任务复用的工作流验收（两个客户端各 3/3）；
- [x] 明确服务重启后的行为（P5.1 进程内记录丢失，旧任务要求重交，不承诺跨进程恢复）；
- [x] 增加并发、取消、超时、重复提交、发布竞态和被替换结果的测试；
- [x] 保持现有分页及查询 resource_id 语义稳定，独立校验任务结果发布版本。

验收：agent 能区分“仍在运行”“超时”“业务失败”和“结果已过期”。

P5.2 已接入有界后台执行与四个公共工具，通过真实 MCP SDK 工作流和执行器测试。
底层同步调用无法强制停止，取消或超时后仍保留执行配额直至实际结束。P5.3 已补齐独立
进程和 HTTP 连接的恢复验收；P5.4 已完成只读查询与恢复判断，P5.5 使用真实 worker 和受控
provider 补齐主动操作验收。证据和边界见 `evaluations/reports/2026-10-27-task-recovery.md`
与 `evaluations/reports/2026-10-27-task-actions.md`。P0 工具路由说明已补齐，下一步推进 P6；
这些抽样验收不代表真实 provider 可用性或全部模型、语言改写均已覆盖。

## P6：1.0 契约冻结

- [x] 冻结主工具名、必填参数、枚举和响应语义；独立快照覆盖全部工具及任务模型；
- [x] 建立有时限的弃用策略；正式通知后至少 90 天、两个后续 minor，移除限后续 major；
- [x] 发布迁移说明和完整示例；旧入口继续支持，尚未启动弃用期；
- [x] 所有公开文档与 `tools/list` 一致；模型、路由与迁移 JSON 示例有测试保护；
- [ ] 三仓 baseline/candidate CI 全部通过；
- [x] 完成第三方 agent 黑盒验收；主规划十题在两个客户端都有实际通过轨迹，整轮与复核分开报告。

验收：第三方调用方不需要阅读源码即可安全升级到 1.0。

契约范围与迁移见 `docs/v1-migration.md`。包发布仍由独立发布流程触发，不能用 envelope
版本推断包版本，也不能把冻结/离线验收等同于真实 provider 可用性。
证据见 `evaluations/reports/2026-10-27-v1-contract.md`。CI 条目以本阶段 PR 的全部检查
通过为合并条件；客户端的临时发现/启动失败仍记录在报告中，不称一次整轮 20/20。

## 1.0 之前暂缓

- 大规模扩展 ISS、卫星、流星雨和日食工具；
- 将单个用户的隐式偏好写入全局排序；
- 在没有真实任务状态机的情况下只返回一个形式上的 `task_id`；
- 接入无法说明来源、时效或许可边界的客流数据。
