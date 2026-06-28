# Agent Development Guidelines

This repository exposes MCP tools for AI agents and requires repo-level conventions for safe, consistent agent updates.

See also `CLAUDE.md` for architecture overview, quick commands, design patterns, known sharp edges, and release process.

## Why this file exists

`AGENTS.md` is the repo-level policy document for:
- how new MCP tools are added
- how agent-facing interfaces are designed
- how the harness validates tool registration and behavior
- how changes are documented and tested

This is not a runtime requirement, but it is the best place for team-level regulation.

## What belongs here

1.  Tool registration rules
2.  Agent-facing interface design
3.  Response / error formatting requirements
4.  Example and harness test expectations
5.  Deployment and local agent testing workflows

## Tool registration conventions

- All MCP tools must be defined under `src/functions/`.
- Each tool module must import `src.server_instance.mcp` and decorate tool entrypoints with `@mcp.tool()`.
- The repository should keep tool registration centralized in `src/main.py` by importing tool modules there.
- When explicit `@mcp.tool(name=..., description=...)` metadata is provided, that metadata takes precedence over the function name and docstring and should be treated as the public contract.
- Example domains:
  - `src/functions/celestial/impl.py`
  - `src/functions/metadata/impl.py`
  - `src/functions/planning/impl.py`
  - `src/functions/weather/impl.py`
  - `src/functions/places/impl.py`
  - `src/functions/time/impl.py`

## Agent-facing interface rules

- All tools must return JSON-serializable data.
- Use `src.response.format_response(...)` for standard response wrapping.
- Business validation failures that remain inside normal tool execution should return the structured `{error, _meta}` payload shape instead of ad hoc dicts.
- Dates and times should be returned as ISO strings whenever possible.
- Keep tool argument names clear and stable; renames should be treated as breaking changes.
- Add new tools only after verifying the new interface is agent-friendly and documented.

## Error handling

- Use `src.response.MCPError` for errors that should be surfaced cleanly to agents.
- Standard error codes include:
  - `INVALID_COORDINATES`: Invalid latitude/longitude values
  - `INVALID_TIMEZONE`: Invalid timezone string
  - `INVALID_TIME_FORMAT`: Invalid time string format
  - `MISSING_API_KEY`: Missing required API credentials
  - `API_AUTH_FAILURE`: API authentication failed
  - `API_TIMEOUT`: API request timed out
  - `API_RATE_LIMIT`: API rate limit exceeded
  - `EXTERNAL_API_ERROR`: External API returned error
  - `NETWORK_ERROR`: Network connectivity issues
  - `CONFIGURATION_ERROR`: Configuration problems
- Avoid raising raw exceptions from tools; catch and translate them into structured MCPError responses.
- Prefer translating input and validation failures at the boundary helper level so tool functions stay simple; avoid scattering repetitive `try/except` blocks across individual tool implementations.
- Weather tools include automatic retry logic for network failures (up to 3 attempts with exponential backoff).
- Tool failures should be explicit and actionable for the calling agent.

## Harness engineering requirements

- Use `pytest` for all harness and integration tests.
- Keep tests under `tests/` and exercise both registration and tool execution.
- Existing harness patterns:
  - `tests/test_integration.py` validates tool registration via `mcp._tool_manager._tools`
  - `tests/test_serialization.py` validates the JSON response shape
  - `tests/test_mcp_client.py` validates `tools/list`, `tools/call`, and SSE request-id behavior
  - `tests/test_server_instance.py` validates metadata registry stability and catalog copy semantics
  - `tests/test_structured_errors.py` validates business error payload normalization
- When adding a new tool, add at least one test that:
  1. imports the tool module so it is registered
  2. verifies the tool exists on `mcp`
  3. verifies the tool returns correct JSON structure
  4. verifies any new agent-facing metadata stays aligned with `tools/list` / catalog expectations when applicable

## Agent development workflow

### Local development

1.  Install project dependencies:
    ```bash
    uv sync
    source .venv/bin/activate
    ```
2.  Start the MCP server locally:
    ```bash
    python -m src.main --mode shttp --port 3001 --path /shttp
    ```
    Prefer `shttp`, `sse`, or `local`. `dev` mode has been removed because `run_dev()` is no longer available in current FastMCP versions.
3.  Use examples for agent integration patterns:
    - `examples/shttp_tools_demo.py`
    - `examples/stream_http_analysis_area.py`
    - `examples/code_execution_orchestration.py`

### Testing the agent surface

- Run the full harness:
  ```bash
  pytest tests/
  ```
- Add smoke tests for any new agent interaction style or transport mode.
- If you add a new transport mode or agent integration path, document it in `README.md` and add an example script.

## Documentation and repo hygiene

### 文档体系

| 文档 | 定位 | 受众 |
|------|------|------|
| `README.md` | 工具目录、特性总览、安装与使用 | 所有用户（agent 开发者、最终用户） |
| `AGENTS.md` | 开发规范、注册约定、错误处理规则 | 本 repo 开发者 |
| `docs/ROADMAP.md` | 能力面状态、已完成 / 计划中的工作 | 本 repo 开发者、PM |
| `docs/bridge-boundary.md` | `placefinder` bridge 的接口、职责边界与调用链 | 跨 repo 开发者 |
| `docs/analysis-area-semantics.md` | `analysis_area` 的分页、缓存、`resource_id` 语义 | agent 集成者、本 repo 开发者 |
| `docs/workspace-action-checklist.md` | workspace 级任务清单与验收标准 | 本 repo 开发者 |
| `docs/workspace-technical-map.md` | workspace 级架构总览与技术债热点 | 本 repo 开发者 |

### 何时更新哪份文档

| 变更类型 | 必须更新 | 可选更新 |
|---------|---------|---------|
| 新增 MCP 工具 | `README.md`（Available Tools）、`docs/ROADMAP.md`（Recently completed） | `AGENTS.md`（如涉及新 domain） |
| 修改工具参数或返回值 | `README.md`（Available Tools）、`docs/ROADMAP.md` | `docs/analysis-area-semantics.md`（如涉及分页/缓存语义） |
| 删除工具 | `README.md`、`docs/ROADMAP.md`、`AGENTS.md` | — |
| Bridge 层变更 | `docs/bridge-boundary.md` | `docs/workspace-technical-map.md` |
| 新增下层能力到 bridge | `docs/bridge-boundary.md` | `docs/workspace-technical-map.md` |
| 错误码新增 | `AGENTS.md`（Error handling）、`README.md`（Error Handling） | — |
| 协议/transport 变更 | `AGENTS.md`、`docs/ROADMAP.md` | `README.md` |
| 缓存策略变更 | `docs/analysis-area-semantics.md` | `docs/ROADMAP.md` |

### 最小更新规则

1. **新增 agent-facing 能力**（新工具、新参数、新错误码）→ 必须同步更新 `README.md` + `docs/ROADMAP.md`
2. **删除或重命名** → 必须同步更新 `README.md` + `AGENTS.md` + `docs/ROADMAP.md`
3. **Bridge 层变更** → 必须同步更新 `docs/bridge-boundary.md`
4. **分页/缓存/`resource_id` 语义变更** → 必须同步更新 `docs/analysis-area-semantics.md`
5. **Workspace 级架构变更** → 必须同步更新 `docs/workspace-technical-map.md`

### 同步检查清单

每次发布前执行：

- [ ] `README.md` 的 Available Tools 列表与 `@mcp.tool()` 注册集合一致
- [ ] `docs/ROADMAP.md` 的 Recently completed 反映最新交付
- [ ] `AGENTS.md` 的错误码列表与 `src/response.py:MCPError` 一致
- [ ] 文档中没有引用已删除的文件路径或工具名
- [ ] 示例脚本 (`examples/`) 的参数与工具签名一致

## Future roadmap

See `docs/ROADMAP.md` for the planned agent and harness feature roadmap, including:
- remaining contract hardening for metadata, errors, and transport behavior
- composite planning tools
- streamed large-search support
- expanded astronomy domain features

See `CLAUDE.md` → Known Sharp Edges for current technical debt items including the place-finder bridge `sys.path` manipulation, global cache thread safety, weather provider code duplication, and the Python 3.13+ version constraint.
