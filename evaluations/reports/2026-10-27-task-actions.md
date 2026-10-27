# 第三方客户端主动任务工作流验收 — 2026-10-27

本轮补齐 P5.4 只读恢复判断未覆盖的主动提交与取消。每个客户端分别执行三个固定问题，
每题启动独立客户端和 stdio MCP 服务，不继承任务编号或缓存。

| 客户端 | 版本 | 模型记录 | 工具选择 | 首次调用契约 | 调用证据 | 答案 | 综合通过 |
|---|---|---|---|---|---|---|---|
| Codex CLI | 0.164.0-alpha.11.1 | 请求配置 `gpt-6.1-sol` | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| Claude Code | 2.1.179 | 响应记录 `deepseek-v4-pro` | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |

以上为工具计算结果，合计 6/6。客户端名称不代表模型供应商；Codex 的模型记录来自
请求配置，未独立核实服务内部路由。所有正式运行一次完成，没有重采样。

## 问题与判分

| 场景 | 必须实际执行的流程 | 预期答案 |
|---|---|---|
| `submit-page` | 提交指定请求 → 查询确认成功 → 读取每页一条的第二页 | `Recovery Valley` |
| `cancel-running` | 提交 → 取消返回的任务编号 → 查询确认取消 | `cancelled` |
| `duplicate-cancel` | 连续提交同一请求两次 → 核对编号复用 → 取消 → 查询确认 | `REUSED_AND_CANCELLED` |

判分同时核对服务端调用轨迹和最终答案。首次业务调用须为提交接口；搜索参数必须与
问题一致，后续操作须使用实际返回的任务编号，响应须关联同一资源。分页前必须观察到
成功状态，取消后必须重新查询到取消状态。重复提交须返回同一活动任务，每题实际 provider
调用计数均为一次。猜中答案、改请求、错编号或页码、漏取消、漏确认、额外计算、被阻止的
工具调用及客户端本地命令均不能通过。

逐题问题、答案、调用参数及响应、模型记录、原始日志摘要和源码 SHA256 保存于
[JSON 证据](2026-10-27-task-actions-results.json)。判分器测试使用真实 SDK 轨迹进行
错误注入；另有测试从保存的正式证据重新判分。

## 隔离与适用范围

`task_action_server.py` 公布全部生产工具的原始定义，只允许工具目录和四个任务工具执行。
提交请求必须匹配题目给定的区域及偏好，无关工具和不同请求在执行前被阻止。服务保留
生产适配器、registry、有界线程执行器和缓存；只替换地点 provider，复用 P5.3 的受控
地理结果。取页场景允许 worker 完成；取消场景用独立文件门控保持 worker 运行，取消响应
记录后释放。门控最多等待 30 秒，不依赖真实地理或天气服务。

SDK 回归另外确认实际执行收尾后仍是取消状态、没有结果发布版本，以及重复请求只执行
一次。真实 HTTP 断线与进程重启仍由 P5.3 验证；本轮 AI 客户端经 stdio 连接，不扩展为
AI 已验证跨进程恢复。P5.4 的十个只读问题保持原有范围。

这三个抽样流程补齐了四个任务工具的基本主动操作验收，不代表覆盖所有请求、语言改写、
客户端、模型、真实 provider 可用性或 1.0 冻结要求。

## 复现

```bash
uv run pytest tests/test_task_action_golden.py tests/test_task_recovery_client_scoring.py -q
uv run python -m scripts.run_task_recovery_clients --suite actions --client codex \
  --out-dir <task>/work/codex
uv run python -m scripts.run_task_recovery_clients --suite actions --client claude \
  --out-dir <task>/work/claude
uv run python -m scripts.summarize_task_recovery --suite actions \
  --codex-dir <task>/work/codex --claude-dir <task>/work/claude \
  --out-dir <task>/out --date YYYY-MM-DD
```

沿用既有客户端隔离、模型服务地址和临时 HTTP 配置，不修改用户持久配置。runner 拒绝
复用已有题目目录；默认不传 `--suite` 时仍运行原来的只读恢复题集。
