# MCP Stargazing Roadmap

This roadmap captures future agent-facing, harness, and feature improvements for `mcp-stargazing`.

## Priority 1: Agent discovery and robustness

1.  Tool metadata and discovery
    - Expose each tool's name, description, parameters, and return schema programmatically.
    - Add a tool catalog endpoint or manifest so agents can discover capabilities automatically.
    - Provide a registered discovery tool (`get_tool_catalog`) for agents to inspect available MCP capabilities.
    - Standardize schema documentation in code and generated docs.

2.  Structured errors and retry semantics
    - Use `src.response.MCPError` consistently for agent-visible failures.
    - Define structured error codes for common failure cases:
      - invalid coordinates
      - missing API key / auth failure
      - external API timeout/failure
    - Add retry/fallback behavior for weather and external catalog lookups.

3.  Agent-ready response format
    - Ensure all tools return JSON-serializable data.
    - Strengthen the response wrapper shape and normalize `_meta` content.
    - Add tests for response consistency and schema validation.

## Priority 2: Composite planning tools

1.  `get_best_stargazing_plan`
    - Combine weather, moon phase, visibility, and local light pollution.
    - Return an ordered list of recommended targets plus best observation windows.

2.  `get_best_targets_for_telescope`
    - Provide object recommendations by telescope aperture, season, and difficulty.
    - Include classification: planet, deep-sky, constellation, lunar, and planetary event.

3.  `get_nightly_forecast` enhancements
    - Add more agent-friendly summary fields, like `best_time`, `top_targets`, and `conditions`.
    - Support alternative observer goals: astrophotography, casual viewing, or bright-object observing.

## Priority 3: Big-search and streaming support

1.  Better `analysis_area`
    - Add true incremental streaming support with progress metadata.
    - Support long-running scans and resumable sessions.
    - Add pagination metadata consistency and clear `resource_id` semantics.

2.  Performance and caching
    - Cache regional analysis results when appropriate.
    - Add cache invalidation rules for stale weather and light pollution data.

## Priority 4: Expanded astronomy domain support

1.  Satellite and ISS tracking
    - Add a tool for upcoming ISS passes and bright satellite events.

2.  Meteor shower and eclipse predictions
    - Add tools for next meteor shower peaks and visible eclipse paths.

3.  Constellation / deep-sky seasonal recommendations
    - Add higher-level planning queries like `what is the best summer target tonight?`

## Documentation and test coverage

- Keep `AGENTS.md` and `docs/ROADMAP.md` aligned as the source of repo-level policy.
- Add harness tests in `tests/` for any new agent-facing tool or transport mode.
- Document all new features in `README.md`, `AGENTS.md`, and example scripts.
