# 第三方客户端任务恢复验收 — 2026-10-27

本轮使用 10 个独立、固定的只读问题，验证第三方 AI 如何理解后台任务状态、分页和失效后的
恢复动作。每题启动独立客户端和验收服务，不继承上一题任务；两个客户端各执行全部十题。

| 客户端 | 版本 | 模型记录 | 工具选择 | 首次业务调用契约 | 调用证据 | 答案 | 综合通过 |
|---|---|---|---|---|---|---|---|
| Codex CLI | 0.164.0-alpha.11.1 | 配置为 `gpt-6.1-sol`，沿用现有服务地址 | 10/10 | 10/10 | 10/10 | 10/10 | 10/10 |
| Claude Code | 2.1.179 | 响应记录为 `deepseek-v4-pro` | 10/10 | 10/10 | 10/10 | 10/10 | 10/10 |

以上为工具计算结果，合计 20/20。客户端名称不代表模型供应商；这里没有把 Claude Code
的结果写成 Claude 模型结果。Codex 记录的是请求配置，未另行核实模型服务内部路由。

## 场景与真实调用

| 场景 | 需要核实的事实 | 预期答案 |
|---|---|---|
| 排队 | 已登记任务仍应等待 | `WAIT` |
| 运行 | 未知进度不能当成失败或重新提交 | `WAIT` |
| 执行失败 | 状态接口成功，但业务任务失败 | `NETWORK_ERROR` |
| 超时 | 区分仍运行与 deadline 已到 | `timed_out` |
| 取消后收尾 | 逻辑取消不等于实际执行配额释放 | `WAIT_FOR_EXECUTION` |
| 成功分页 | 确认成功后读取每页 1 条的第 2 页 | `Recovery Valley` |
| 缓存缺失 | 成功元数据不保证结果仍存在 | `RESUBMIT` |
| 发布版本替换 | 不得用同查询的新结果冒充旧任务结果 | `RESUBMIT` |
| runtime 改变 | 旧编号不能跨进程恢复 | `RESUBMIT` |
| 元数据过期 | 区分缓存过期与任务记录过期 | `expired` |

验收服务公布全部 21 个生产工具的原有名称、描述和 schema，调用时仅放行工具目录、
任务状态和任务结果查询。其他工具在执行前被阻止，因此不会访问真实地理服务、提交任务
或取消工作。任务适配器、registry 和缓存行为沿用生产实现；状态、时钟及执行占用元数据
由 fixture 固定，没有启动真实 provider worker。实际并发与进程恢复另由 P5.2/P5.3 覆盖。

判分同时检查服务端实际调用记录和客户端结果。猜中答案、查询错误编号、使用其他工具、
未实际读取指定页，均不能通过。预期的 `TASK_RESULT_EXPIRED` / `TASK_RUNTIME_CHANGED`
是正确观察到的业务错误，计为契约通过，不称为业务执行成功。工具目录发现不计为首次
业务调用；本轮正式记录的首次业务调用均为任务查询工具。

## 判分修正与接入试验

初版判分要求两个缓存场景直接调用取结果接口，Claude Code 因先查状态再取结果而只有
8/10 综合通过，但十个答案均正确。公开描述本来就允许先确认任务成功再取结果，因此修正
为允许两条路径，并要求实际观察到 `TASK_RESULT_EXPIRED`。只有成功状态、没有读取结果
的轨迹仍被拒绝。修正后从同一份调用记录重新判分，没有重采样；JSON 保留初版判分结果。

正式运行前的服务导入失败、模型连接试验和中止的旧慢速 Codex 运行不计入上述分母。
Claude Code 的 MCP 子进程通过 `PYTHONPATH` 取得项目路径。Codex 使用现有模型及服务
地址的独立配置别名，通过本次进程的 HTTP 和 localhost 直连避免代理/连接回退；不改用户
配置文件、不更换凭据。HTTP 设置参考 [OpenAI 官方文档](https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server)。

## 复现与边界

```bash
uv run python -m scripts.run_task_recovery_clients --client codex --out-dir <task>/work/codex
uv run python -m scripts.run_task_recovery_clients --client claude --out-dir <task>/work/claude
uv run python -m scripts.summarize_task_recovery --codex-dir <task>/work/codex \
  --claude-dir <task>/work/claude --out-dir <task>/out --date YYYY-MM-DD
```

汇总证据保存在 [JSON 报告](2026-10-27-task-recovery-results.json)，包含逐题问题、实际答案、
服务端调用及响应、客户端原始日志摘要和源码 SHA256。问题同时保存在
`evaluations/task_recovery_golden.xml`，由测试检查与可执行场景一致。

本轮没有证明真实 provider 可用性、跨进程持久化、AI 主动提交或取消任务的选择能力，
也不代表所有模型或自然语言改写都能通过。两个客户端的历史主规划报告仍保持原有范围。
