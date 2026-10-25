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
