# MCP Stargazing Roadmap

This roadmap tracks the remaining agent-facing, harness, and feature work for `mcp-stargazing`.

## Recently completed foundation work

The following baseline capabilities are already implemented and should no longer be treated as future work:

- **1.0 contract preparation** — A separate full-surface baseline protects all 21 tools, task
  annotations/models, detailed payloads, and envelope semantics. A finite deprecation policy and
  an executable primary-planner migration example preserve legacy callers. See `docs/v1-migration.md`;
  the freeze does not bump or publish the package version.
  Production-adapter black-box coverage now includes all ten planning questions for both clients;
  full runs and targeted rechecks are reported separately in
  `evaluations/reports/2026-10-27-v1-contract.md`, including discovery/startup failures.

- **Public tool routing guidance** — All 21 standard MCP descriptions state when to use the
  tool, when to choose an alternative, required context, returned data, and follow-up actions.
  SDK and real HTTP discovery tests protect these sections and registered follow-up names without
  changing tool schemas or adding a separate catalog routing format. Both installed clients
  passed the three-workflow task regression; scope and evidence are recorded in
  `evaluations/reports/2026-10-27-tool-routing.md`.

- **P5.5 active AI task workflows** — Codex CLI and Claude Code each completed three isolated
  submission/paging, cancellation, and active-query reuse workflows with production task adapters
  and actual background workers. Strict trace grading verifies returned identities, exact
  queries/pages, cancellation confirmation, and one provider execution per case. See
  `evaluations/reports/2026-10-27-task-actions.md` for evidence and scope.

- **P5.4 read-only AI recovery gate** — Codex CLI and Claude Code each completed ten frozen
  status/result questions with verified tool traces and exact answers. The 20/20 gate distinguishes
  execution failure, timeout, physical draining, paging, cache/version loss, and runtime loss.
  See `evaluations/reports/2026-10-27-task-recovery.md` for models, scoring correction, and limits.

- **P5.3 process recovery acceptance** — Real HTTP clients reconnect to running tasks and page
  their results; fresh server processes reject old task IDs after graceful restart or an in-flight
  crash. Explicit resubmission recomputes, while cancelled work cannot publish late results.
  The harness preserves production task execution and replaces only the geographic provider.

- **P5.2 background area analysis** — Four task tools provide bounded submission, polling,
  cancellation, and cached pagination. Physical execution stays bounded after logical cancellation
  or timeout, and guarded publication/revision checks prevent late or replaced results from being
  read as the task's result. Existing synchronous tools and the pre-1.0 schemas remain compatible.

- **Pre-1.0 schema baseline** — The existing 17 SDK-generated tool schemas, primary/composite
  planning and area-result models, default response envelopes, and public error codes are saved
  in `tests/public_schema_baseline.json`. Application and real MCP protocol tests protect the
  baseline; new tools can be added without silently changing existing contracts.

- **P5.1 internal task lifecycle** — A bounded, thread-safe area-task registry now defines
  atomic worker claims, duplicate submission, cancellation, deadline, expiry, immutable status
  snapshots, and explicit runtime-loss behavior. This foundation does not schedule workers or
  register task tools; public task metadata remains reserved until the execution adapter lands.

- **P3.6 popularity ownership** — Composite planners request SPF place scores with both
  popularity preference flags disabled, then apply the user's preferences once in MCP.
  Standalone `analysis_area` retains SPF-owned preference scoring; planning resource IDs
  reference the neutral area query, so preferred area caches cannot contaminate planning.

- Tool discovery is available through the registered `get_tool_catalog` tool.
- `light_pollution_map` provides per-coordinate light pollution data (Bortle class, brightness, SQM) through a dedicated MCP tool.
- Tool metadata is exposed programmatically and kept aligned with `tools/list`.
- Business validation failures are normalized into the standard `{error, _meta}` payload shape.
- Weather tools already include retry behavior for transient network failures.
- `analysis_area` now has explicit pagination validation and stable `resource_id` semantics based only on non-pagination query parameters.
- `analysis_area` and `get_best_stargazing_plan` expose popularity preference parameters (`avoid_popular_spots`, `prefer_quiet_at_night`, `popularity_radius_km`). Area cache keys reflect the actual search parameters; composite planning always searches with both preference flags disabled.
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

- The pytest suite covers all 21 MCP tools, including success, structured-error, edge-case, serialization, protocol, documentation-contract, and deployment-config paths.
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
- ✅ Audit all 21 public tools for routing, infrastructure leakage, and compatibility risk;
  publish use/do-not-use, prerequisites, results, and follow-up guidance in standard descriptions.
- ✅ Capture the pre-1.0 schema baseline with SDK and real `tools/list` checks.
- ✅ Define finite deprecation rules and review changes against independent historical and 1.0 baselines.

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
- ✅ Align ranking factors and explanations: `score_breakdown.factor_contributions` now exposes
  the signed place, weather, popularity, and accessibility contributions used by ranking, while
  recommendation reasons surface the same active weather-window, spatial-cloud, moonlight, and
  accessibility signals.
- ✅ Make SPF and MCP ownership of popularity scoring explicit: SPF provides neutral place
  scores and heuristic evidence to composite planners; MCP owns the preference adjustment.
  Screening and final evaluation each compute a score from the neutral baseline, without
  accumulating the screening adjustment. Standalone area analysis keeps SPF-owned scoring.

## Priority 5: Evaluation and long-running work

- ✅ Ten read-only planning golden scenarios cover tool selection, ranking, explanations,
  partial-provider degradation, empty results, missing night windows, historical dates, and both
  stable equipment presets.
- ✅ Codex CLI and Claude Code each selected the candidate primary planner on the first actual tool
  call and returned the expected HOPE D60 + ASI2600MC Air answer (2/2 representative smoke).
- ✅ P5.1 defines the internal lifecycle and task/resource identity boundary, with deterministic
  concurrency, timeout, retention, and runtime-loss tests. See `docs/task-lifecycle.md`.
- ✅ P5.2 binds bounded background execution, status polling, cancellation, and paged result
  retrieval through four application-level tools, activating optional task metadata only there.
- ✅ P5.3 verifies disconnect/reconnect, cross-connection pagination, cancellation, actual process
  restart, and in-flight process loss through the real HTTP transport.
- ✅ P5.4 verifies third-party AI read-only task-tool selection and recovery decisions.
- ✅ P5.5 verifies third-party AI submission, status-confirmed pagination, cancellation, and active
  duplicate reuse through three isolated workflows per client. Real provider availability and
  broader natural-language/model coverage remain outside this gate.
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
- ✅ Harness tests exist for all 21 tools: success, error, edge cases, and documentation contracts.
- ✅ All new features documented in `README.md`, `AGENTS.md`, and `CLAUDE.md`.
- Cross-repository compatibility is enforced by the wheel-level dependency-chain CI. Per-repository documentation is checked by the owning repository's own contract tests.
- ✅ Example scripts are available for `get_telescope_targets` and `get_shooting_plan`.
