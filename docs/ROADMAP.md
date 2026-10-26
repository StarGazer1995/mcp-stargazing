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
- `analysis_area` and `get_best_stargazing_plan` now expose popularity preference parameters (`avoid_popular_spots`, `prefer_quiet_at_night`, `popularity_radius_km`), and those parameters participate in `resource_id` / cache-key generation.
- Place results now surface popularity heuristic fields (`static_popularity_risk_score`, `night_quiet_likelihood_score`, `temporal_popularity_confidence`, and related notes/signals) from `stargazing-place-finder`.
- MCP protocol tests now verify `tools/list` / catalog consistency and SSE JSON-RPC request id preservation.
- `get_celestial_rise_set` now supports explicit `calendar_day` and `next_events` scopes, making cross-midnight sunrise/sunset semantics unambiguous.
- `get_nightly_forecast` and planning candidates now expose a structured civil-dark `NightWindow`.
- `plan_stargazing_session` is now the preferred third-party-agent entry point, returning a
  decision, alternatives, evidence, uncertainties, material missing inputs, ranking-reversal
  conditions, and next actions without exposing provider or database configuration.
- `get_best_stargazing_plan` now provides an MVP regional planning flow that combines candidate places, weather summaries, moon phase, and top targets, and can apply a planning-layer popularity re-rank with explanation fields when popularity preferences are enabled.
- Cross-repository CI now compares baseline and candidate wheel builds across
  `stargazing-core`, `stargazing-place-finder`, and `mcp-stargazing`. See
  `docs/dependency-chain-ci.md`.
- Weather provider orchestration now uses a shared adapter registry, and the legacy SPF path-injection compatibility layer is removed.

### Bridge and weather cleanup (completed 2026-07)

- **SPF bridge import compatibility** — `src/placefinder.py` now prefers
  `stargazingplacefinder` namespaced imports and only falls back to legacy
  source-root path prioritization for older published SPF wheels.
- **SPF namespaced wrappers** — merged SPF support for
  `stargazingplacefinder.config` / `stargazingplacefinder.models`, removing the
  old top-level import requirement from the primary runtime path.
- **Shared weather transport helper** — QWeather, Open-Meteo, and wttr now share
  request execution and MCP error translation through
  `src/functions/weather/providers/_http.py`, while `qweather_interaction.py`
  stays a thin URL-building wrapper.
- **Moon rise/set semantics** — lunar rise and set are now distinguished by
  horizon crossing direction rather than timestamp ordering, preserving valid
  same-day “set before rise” cases.

### Geocoding cost decoupling (completed 2026-09)

- **Offline CJK gazetteer is the default tier** — `src/data/china_divisions.json`
  ships province/city/district administrative divisions (~3200 rows) and
  resolves Chinese place names such as `浙江安吉` offline with no API key and
  no network call.
- **Amap is now opt-in only** — `AMAP_KEY` alone no longer routes CJK queries
  to the paid Amap Geocoding API. Deployments must explicitly list `amap` in
  `GEOCODER_PROVIDERS` (with `AMAP_KEY` set) to re-enable it.
- **Configurable provider order** — `GEOCODER_PROVIDERS` accepts
  `gazetteer`, `photon`, `nominatim`, and `amap`. The default chain is
  gazetteer → Photon → Nominatim for CJK and Photon → Nominatim otherwise.
- Gazetteer provenance and coordinate datum (GCJ-02) documented in
  `src/data/README.md`; tests added for provider ordering, Amap opt-in
  behaviour, and gazetteer matching/ambiguity handling.

### Phase 4 — Telescope & shooting plan tools (completed 2026-07)

- **`get_telescope_targets`** — Match deep-sky objects against telescope optics (focal length, aperture, sensor, filter). Returns ranked targets with suitability scores, FOV fit, surface brightness, and mosaic recommendations.
- **`get_shooting_plan`** — Generate an optimized single-night imaging schedule: time-ordered exposure slots with meridian flip awareness, moon separation, and altitude curves.
- Both tools integrate with `stargazing-core` for shared telescope optics computation.
- Full test coverage: 6 success-path tests + 5 error-path/edge-case tests (invalid coords, time, timezone, empty targets).

### Dependency & deployment (completed 2026-07)

- **`stargazing-core` published to PyPI (v0.1.0)** — Shared dependency resolved from a single registry source. Both `mcp-stargazing` and `stargazing-place-finder` declare `stargazing-core>=0.1.0`. No `[tool.uv.sources]` path overrides needed in committed config.
- **Docker dual-service** — Production container runs MCP server (:3001) + SPF web UI (:5001) via supervisord. Both services share the same `uv`-managed venv.
- **Supervisor config validation** — 15 tests in `test_supervisord_config.py` verify supervisor config ↔ Dockerfile consistency (ports, programs, paths, autorestart).

### Test coverage

- The pytest suite covers all 17 MCP tools, including success, structured-error, edge-case, serialization, protocol, documentation-contract, and deployment-config paths.
- `test_mcp_tools.py` centralizes tool-wrapper coverage.
- `test_supervisord_config.py` validates deployment config consistency.

## Product direction: third-party agent first

The next milestone is not a wider astronomy-tool catalog. It is a stable decision backend that
an unfamiliar third-party agent can call without understanding repository internals, provider
selection, or server filesystem configuration. The target contract and implementation checklist
live in `docs/agent-contract.md` and `docs/workspace-action-checklist.md`.

## Priority 1: Agent contract baseline

- ✅ Standard response and error envelopes are covered by contract tests.
- ✅ Tool registration, `tools/list`, catalog output, and README names are aligned.
- ✅ Observation-style profiles, popularity explanations, night windows, and multi-night planning
  establish the current planning baseline.
- ✅ Define the target third-party-agent contract, three-repository technical map, and staged
  implementation checklist.
- Audit all 17 public tools for agent routing guidance, infrastructure leakage, and compatibility
  risk.
- Capture the pre-1.0 schema baseline and define deprecation rules.

## Priority 2: Application-service boundary

- ✅ Extracted single-night and multi-night validation, orchestration, ranking, and explanation into
  the transport-independent `PlanningService`; direct service tests cover success and provider
  degradation.
- ✅ Multi-night planning now reuses single-night application logic directly instead of calling a
  second public planning wrapper.
- ✅ Place analysis, coordinate weather, and nightly forecast expose transport-free internal
  capabilities; planning no longer calls another public tool wrapper's `.fn`. A source contract
  test prevents this dependency from returning.
- ✅ Registered `plan_stargazing_session` as the preferred primary entry after its application
  models, golden scenarios, migration plan, and multi-client black-box validation passed.
- Preserve current public behavior while the existing single-night and multi-night tools serve as
  compatibility entries through at least one documented migration cycle.
- Keep provider selection, credentials, database paths, and cache internals out of the new primary
  entry point.

## Priority 3: Agent-native planning contract

- ✅ The registered primary contract accepts a place name, center/radius, or exact bounds,
  plus date range, observation goal, equipment preset, and explicit user constraints.
- ✅ `AgentPlanningResult` returns a first-class decision plus alternatives, exact score breakdown,
  evidence, uncertainties, materially missing inputs, ranking-reversal conditions, and next actions.
- ✅ Provider selection and database paths remain server policy; normalized defaults are echoed in
  the request section and protected by contract tests.
- ✅ Seestar S50, HOPE D60 + ASI2600MC Air, and custom optics are normalized with explicit
  overrides and drive target matching for the selected session.
- ✅ Ten frozen planning scenarios and representative Codex/Claude black-box acceptance passed
  before production registration; the bbox-first planning tools remain compatibility entries.

## Priority 4: Decision quality

- ✅ Replaced early static candidate truncation with a bounded place-recall pool before final
  candidate truncation; a regression test proves a weather winner outside the static top-N can
  become the first recommendation.
- ✅ Replaced the bounded downstream evaluation with low-cost dynamic weather screening and
  expensive night-window/target evaluation only for the strongest internal candidates; regression
  coverage verifies the recall pool is screened while downstream calls stay bounded.
- ✅ Use the spatial weather primitives already available in `stargazing-core`: one regional
  cloud-cover grid is sampled at the recall candidates and blended into ranking, with graceful
  fallback to point weather when the spatial model is unavailable.
- ✅ Replace the best-single-hour heuristic with continuous observing windows: hourly forecasts
  are constrained to civil darkness, grouped by forecast continuity, and scored with cloud,
  precipitation, wind, moon illumination, and available target-altitude signals. The additive
  `end_time`, `duration_hours`, and `quality_score` fields keep the old hourly fields compatible.
- Make SPF and MCP ownership of popularity scoring explicit so that the same heuristic is not
  accidentally counted twice.

## Priority 5: Evaluation and long-running work

- ✅ Ten read-only planning golden scenarios cover tool selection, ranking, explanations,
  partial-provider degradation, empty results, missing night windows, historical dates, and both
  stable equipment presets.
- ✅ Codex CLI and Claude Code each selected the candidate primary planner on the first actual tool
  call and returned the expected HOPE D60 + ASI2600MC Air answer (2/2 representative smoke).
- Define a real task lifecycle before activating the reserved `task_id` / `progress` fields for
  long-running area analysis.
- Preserve paging and `resource_id` semantics while adding polling, resumption, expiry, and
  restart behavior.

## Deferred until the decision contract is stable

- Satellite and ISS tracking.
- Meteor-shower and eclipse tools.
- Broad expansion of independent astronomy lookup tools.
- Real-time crowd data without stable provenance, freshness, and licensing semantics.

## Documentation and test coverage

- `AGENTS.md`, `README.md`, `docs/ROADMAP.md`, and the agent-contract documents are checked for
  current paths and dependency floors.
- ✅ Harness tests exist for all 17 tools: success, error, edge cases, and documentation contracts.
- ✅ All new features documented in `README.md`, `AGENTS.md`, and `CLAUDE.md`.
- Cross-repository compatibility is enforced by the wheel-level dependency-chain CI. Per-repository documentation is checked by the owning repository's own contract tests.
- ✅ Example scripts are available for `get_telescope_targets` and `get_shooting_plan`.
