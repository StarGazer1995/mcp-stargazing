# 公共工具路由说明验收 — 2026-10-27

本轮完成 P0 最后一项：全部公开工具在标准 MCP description 中说明适用场景、误用边界、
前置输入、返回内容和后续操作。说明使用固定标题 `Use when:`、`Do not use when:`、
`Requires:`、`Returns:` 和 `Follow-up:`，不增加另一套 catalog 字段。

## 发现面与兼容性

真实 SDK 与 HTTP `tools/list` 均验证了全部 21 个工具的说明，确认每个后续工具引用确实
已注册。`get_tool_catalog` 保持原有形状：普通工具的 `description` 仍是首行摘要，
完整说明来自 `docstring`；显式 decorator description 优先且已包含完整说明。

重点覆盖的易误用边界包括：星座中心位置与任意坐标星座归属、服务器本地时间与观测地
时间、地平线以上行星与完整观测条件、升落事件的日历日/后续事件范围、兼容规划入口与
主入口、同步区域候选与后台任务，以及轮询、取页和取消的区别。

公共 schema 基线与真实协议基线测试均通过，历史快照未刷新。对改动模块的 AST 比较
确认生产差异仅为 docstring 或 decorator description；工具参数、注解、执行逻辑、
响应和错误码保持不变。完整回归 487 项通过，Ruff 与 Bandit 通过。

工作区开始前已有 `tests/test_area_task_tools.py` 改动，与上一阶段相同，仍原样保留并
排除提交。完整本地回归使用已提交版本的独立测试副本替代该文件，其余测试正常执行；
此处的通过数不声称原有改动文件已经修复。

## 客户端回归

沿用 P5.5 的三个隔离场景，检查更新后的描述是否影响主动任务路由。每个客户端分别运行
提交/确认成功后分页、提交/取消/查询确认、重复提交复用/取消/查询确认；每题启动独立
进程。生产任务适配器与实际 worker 保留，地理 provider 使用受控结果。

| 客户端 | 版本 | 模型记录 | 选工具 | 首次契约 | 调用证据 | 答案 | 综合通过 |
|---|---|---|---|---|---|---|---|
| Codex CLI | 0.164.0-alpha.11.1 | 请求配置 `gpt-6.1-sol` | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| Claude Code | 2.1.179 | 响应记录 `deepseek-v4-pro` | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |

以上为工具计算结果，合计 6/6；没有重采样。客户端名称不代表模型供应商，Codex 内部
模型路由未另行核实。判分复用原有严格规则，检查实际请求、任务编号、资源编号、页码、
取消确认、单次 provider 执行与最终答案。猜中答案不能代替实际工具调用。

[JSON 证据](2026-10-27-tool-routing-results.json)保存逐题调用、答案、模型记录、原始日志
摘要、全部标准 description 快照和源码指纹。该客户端回归仅覆盖三个任务工作流，不能
扩展为两个 AI 客户端已分别验证全部工具，或证明真实 provider 可用性。

## 复现

```bash
uv run pytest tests/test_tool_routing.py tests/test_public_schema_baseline.py tests/test_mcp_client.py -q
uv run python -m scripts.run_task_recovery_clients --suite actions --client codex \
  --out-dir <task>/work/codex
uv run python -m scripts.run_task_recovery_clients --suite actions --client claude \
  --out-dir <task>/work/claude
uv run python -m scripts.summarize_task_recovery --suite actions \
  --codex-dir <task>/work/codex --claude-dir <task>/work/claude \
  --out-dir <task>/out --date YYYY-MM-DD
```

P0 路由说明完成后，下一阶段为 P6 的有时限弃用策略、兼容/迁移文档和 1.0 契约冻结验收。
