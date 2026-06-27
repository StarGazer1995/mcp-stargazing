# MCP Stargazing Roadmap

This roadmap tracks the remaining agent-facing, harness, and feature work for `mcp-stargazing`.

## Recently completed foundation work

The following baseline capabilities are already implemented and should no longer be treated as future work:

- Tool discovery is available through the registered `get_tool_catalog` tool.
- `light_pollution_map` provides per-coordinate light pollution data (Bortle class, brightness, SQM) through a dedicated MCP tool.
- Tool metadata is exposed programmatically and kept aligned with `tools/list`.
- Business validation failures are normalized into the standard `{error, _meta}` payload shape.
- Weather tools already include retry behavior for transient network failures.
- `analysis_area` now has explicit pagination validation and stable `resource_id` semantics based only on non-pagination query parameters.
- MCP protocol tests now verify `tools/list` / catalog consistency and SSE JSON-RPC request id preservation.
- `get_best_stargazing_plan` now provides an MVP regional planning flow that combines candidate places, weather summaries, moon phase, and top targets.

## Priority 1: Finish contract hardening

1.  Schema and documentation consistency
    - Keep tool descriptions, parameter docs, and return-shape documentation synchronized across code, `README.md`, and generated tool metadata.
    - Add stronger field-level checks for tool metadata drift when new tools are introduced.

2.  Error contract consistency
    - Continue migrating agent-visible validation failures to `src.response.MCPError`.
    - Reduce mixed error paths where some failures return business payloads while others surface as transport-level JSON-RPC errors.
    - Keep error codes stable and documented for calling agents.

3.  Transport and protocol robustness
    - Extend protocol-level tests beyond the current SHTTP/SSE request-id and `tools/list` coverage.
    - Add focused coverage for any future transport-specific behavior changes.

## Priority 2: Composite planning tools

1.  `get_best_stargazing_plan`
    - Extend the shipped MVP with richer ranking policies, observer preferences, and stronger explanation fields.
    - Improve how the planner balances weather quality, moonlight, place quality, and target mix.

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
    - Preserve stable paging semantics while adding streaming or resumable workflows.

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

- Keep `AGENTS.md`, `README.md`, and `docs/ROADMAP.md` aligned whenever the tool surface changes.
- Add harness tests in `tests/` for any new agent-facing tool, response contract, or transport mode.
- Document all new features in `README.md`, `AGENTS.md`, and example scripts.
