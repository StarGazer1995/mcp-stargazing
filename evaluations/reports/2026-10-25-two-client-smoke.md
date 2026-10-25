# Two-client black-box smoke — 2026-10-25

## Scope

Both clients received the same natural-language question about deep-sky imaging around Anji on
2024-10-02 with the `hope_d60_asi2600mc_air` preset. They connected to the evaluation-only stdio
server, which exposed the production 16 tools plus the draft `plan_stargazing_session` tool.

Expected single answer: `M31`.

## Results

| Client | Version | First selected MCP tool | First actual call | Answer | Result |
|---|---|---|---|---|---|
| Codex CLI | 0.164.0-alpha.11.1 | `plan_stargazing_session` | success | `M31` | pass |
| Claude Code | 2.1.179 | `plan_stargazing_session` | success | `M31` | pass |

Metrics for this representative smoke:

- tool selection accuracy: 2/2;
- first actual tool-call success: 2/2;
- exact-answer accuracy: 2/2.

Codex required its read-only MCP call to be run with client-side auto approval. An initial
configuration probe selected the correct tool and built the correct request, but was denied by the
client's `never` approval policy; it is not counted as an executed acceptance case. After the
documented client configuration was corrected, the first actual call succeeded.

Claude Code was limited to tools from the `stargazing` MCP server. It selected the draft primary
tool from all 17 advertised tools, supplied the nested location, date, observing style, and equipment
preset on the first call, and returned the exact expected value.

## Boundaries

This is representative multi-client acceptance, not a claim that both clients completed every
golden question. All ten questions are independently executed by
`tests/test_agent_planning_golden.py`; the client smoke covers the highest-risk new equipment preset
and primary-tool selection path.

Codex MCP configuration followed the official OpenAI documentation for local MCP servers:
<https://developers.openai.com/learn/docs-mcp>.
