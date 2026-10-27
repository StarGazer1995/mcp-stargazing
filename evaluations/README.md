# Agent planning evaluation

This directory preserves the frozen gate that qualified `plan_stargazing_session` for production
registration.

- `planning_golden.py` defines ten independent, read-only, frozen scenarios and their dependency
  evidence.
- `planning_golden.xml` is the human-readable evaluation set. Every answer is a single stable value.
- `server.py` starts an evaluation-only stdio MCP server. It exposes the 16 production support and
  compatibility tools as realistic alternatives, then substitutes a frozen-data adapter for the
  production primary planning entry point.
- `tests/test_agent_planning_golden.py` checks first-call contract success, ranking, score/explanation
  alignment, actionable degradation, required observing styles, and both stable equipment presets.

Run the deterministic gate:

```bash
pytest tests/test_agent_planning_golden.py -q
```

The evaluation server is read-only and performs no network access:

```bash
python -m evaluations.server
```

The production server now registers the qualified primary entry point; this evaluation adapter
remains deterministic and network-free. Black-box client reports belong under
`evaluations/reports/`; do not treat a client as passing unless it selects
`plan_stargazing_session`, succeeds on its first tool call, and returns the exact expected value.

## Background-task recovery acceptance

`area_task_server.py` is a separate integration harness. It imports all production tool
registrations and keeps the production task registry, executor, cache, adapters, and lifespan.
Only the place-computation provider is replaced with deterministic results and filesystem gates
under an explicitly supplied test directory. It adds no test-control MCP tools and makes no
external provider requests.

```bash
uv run pytest tests/test_area_task_recovery.py -q
```

The tests connect over real streamable HTTP to child server processes. They cover disconnect
and reconnect while running, active-query deduplication, paged reads across new connections,
logical cancellation with physical work still draining, and registry/cache loss after actual
restart. A separate case crashes a child during analysis and verifies that a fresh process
rejects its old task ID and recomputes only after explicit resubmission.

This is protocol/process recovery acceptance. It does not claim a third-party AI selected the
new task tools correctly; the historical two-client planner report remains scoped to its original
frozen planner scenario.

## Third-party AI recovery decisions

`task_recovery_golden.py` and its matching XML define ten independent read-only questions.
`task_recovery_server.py` exposes all 21 production tool definitions, seeds frozen task/cache
states, and blocks non-query execution before it reaches providers. The production task adapters
remain in use. This fixture does not run real geographic work or reproduce process failure.

Run `uv run pytest tests/test_task_recovery_golden.py tests/test_task_recovery_client_scoring.py`.
The client runner and evidence summarizer are documented in the
[2026-10-27 report](reports/2026-10-27-task-recovery.md). Both Codex CLI and Claude Code completed
all ten questions; the report records model identity, grading corrections, setup probes, and limits.
AI submission/cancellation workflows remain separate from this read-only gate.

## Third-party AI active task workflows

`task_action_golden.py` defines three independent submission/paging, cancellation, and duplicate
submission/cancellation questions. `task_action_server.py` retains the production task service,
actual worker execution, cache, and tool definitions. It reuses the P5.3 controlled provider,
permits only task operations on the specified query, and audits each tool response and provider
call count. Other tools remain discoverable but cannot execute.

Run `uv run pytest tests/test_task_action_golden.py -q`. Use the existing client runner and
summarizer with `--suite actions` to run the active gate; their default read-only suite is
unchanged. Both installed clients completed all three questions. Reproduction, trace grading,
and limits are recorded in the [active-workflow report](reports/2026-10-27-task-actions.md).
