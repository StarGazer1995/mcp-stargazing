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

### Phase 4 — Telescope & shooting plan tools (completed 2026-07)

- **`get_telescope_targets`** — Match deep-sky objects against telescope optics (focal length, aperture, sensor, filter). Returns ranked targets with suitability scores, FOV fit, surface brightness, and mosaic recommendations.
- **`get_shooting_plan`** — Generate an optimized single-night imaging schedule: time-ordered exposure slots with meridian flip awareness, moon separation, and altitude curves.
- Both tools integrate with `stargazing-core` for shared telescope optics computation.
- Full test coverage: 6 success-path tests + 5 error-path/edge-case tests (invalid coords, time, timezone, empty targets).

### Dependency & deployment (completed 2026-07)

- **`stargazing-core` published to PyPI (v0.1.0)** — Shared dependency resolved from a single registry source. Both `mcp-stargazing` and `stargazing-place-finder` declare `stargazing-core>=0.1.0`. No `[tool.uv.sources]` path overrides needed in committed config.
- **Docker dual-service** — Production container runs MCP server (:3001) + SPF web UI (:5001) via supervisord. Both services share the same `uv`-managed venv.
- **Supervisor config validation** — 15 tests in `test_supervisord_config.py` verify supervisor config ↔ Dockerfile consistency (ports, programs, paths, autorestart).

### Test coverage (completed 2026-07)

- **265 tests across 26 files** — every one of 15 MCP tools has `.fn`-level test coverage including success, error, and edge-case paths.
- `test_mcp_tools.py` (41 tests) — centralized tool wrapper tests.
- `test_supervisord_config.py` (15 tests) — deployment config validation.

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

2.  Telescope tool improvements
    - Add coordinate validation before `EarthLocation` construction in `get_telescope_targets` and `get_shooting_plan` — currently raw astropy `TypeError` leaks instead of structured `MCPError.INVALID_COORDINATES`.
    - Add telescope preset lookup (e.g., `telescope='RedCat51'` → auto-fill focal_length, aperture).
    - Support multi-night shooting plans beyond single-session scheduling.

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
