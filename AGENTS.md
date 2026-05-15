# Agent Development Guidelines

This repository exposes MCP tools for AI agents and requires repo-level conventions for safe, consistent agent updates.

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
- Example domains:
  - `src/functions/celestial/impl.py`
  - `src/functions/weather/impl.py`
  - `src/functions/places/impl.py`
  - `src/functions/time/impl.py`

## Agent-facing interface rules

- All tools must return JSON-serializable data.
- Use `src.response.format_response(...)` for standard response wrapping.
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
- Weather tools include automatic retry logic for network failures (up to 3 attempts with exponential backoff).
- Tool failures should be explicit and actionable for the calling agent.

## Harness engineering requirements

- Use `pytest` for all harness and integration tests.
- Keep tests under `tests/` and exercise both registration and tool execution.
- Existing harness patterns:
  - `tests/test_integration.py` validates tool registration via `mcp._tool_manager._tools`
  - `tests/test_serialization.py` validates the JSON response shape
- When adding a new tool, add at least one test that:
  1. imports the tool module so it is registered
  2. verifies the tool exists on `mcp`
  3. verifies the tool returns correct JSON structure

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

- Document new tools in `README.md` and `AGENTS.md` when they affect agent-facing behavior.
- Keep example scripts updated when the tool surface changes.
- Keep the `tests/` harness up to date with any interface changes.
- If a tool is removed, update both `README.md` and `AGENTS.md` to reflect the change.

## Future roadmap

See `docs/ROADMAP.md` for the planned agent and harness feature roadmap, including:
- tool metadata and discovery, including a registered discovery tool (`get_tool_catalog`)
- structured error handling
- composite planning tools
- streamed large-search support
- expanded astronomy domain features
