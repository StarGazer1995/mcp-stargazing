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

## 1.0 primary-planner gate

`v1_planning_server.py` imports all production registrations and preserves their descriptions,
schemas, annotations, and primary adapter. Only its application dependency builder is dispatched
to the existing ten frozen planning scenarios; non-planning execution is blocked before providers.
`v1_planning_golden.py` grades exact requests, one actual primary call, the answer observed in
the returned model, and the client's final answer. Local command/file access cannot qualify.

Run `uv run pytest tests/test_v1_planning_clients.py -q`. The existing runner and summarizer accept
`--suite planning`; earlier recovery/actions suites keep their defaults and behavior. This gate
does not claim live provider availability or coverage of all natural-language paraphrases.
The [P6 report](reports/2026-10-27-v1-contract.md) preserves the initial unnecessary lookup,
the description fix, the full-run discovery failures, and separate successful rechecks.


## Imaging quality, latency and forecast verification

Run the fixed quality gate with `uv run pytest tests/test_imaging_quality.py`.
The versioned cases in `imaging_quality.py` test thick cloud layers, windy/rainy weather,
missing fields, short or broken forecasts, dawn-only clearing and absent astronomical darkness.
They are deterministic policy tests, not field validation. The older planning fixtures now
include explicit zero precipitation for their frozen clear-weather cases; expected ranking
answers and schema snapshots are not rewritten.

```bash
uv run python -m evaluations.planning_benchmark --mode frozen --repeats 3 --out-dir "$TASK_DIR/out/frozen"
uv run python -m evaluations.planning_benchmark --mode live --url http://localhost:3001/shttp --requests "$TASK_DIR/work/requests.json" --repeats 3 --label deployment-version --out-dir "$TASK_DIR/out/live"
```

Live input is an array of `{ "id": "case-name", "request": { ... } }`; optionally add
`expected_decision: true/false` for a genuinely known expectation. Unknown expectations remain
ungraded. The JSON report separates execution success from expectation checks, includes each
attempt and its start time, and reports median/p95 (nearest-rank p95, descriptive for small
samples). First repetition is not proof of a cold cache. Preserve deployment label, requests,
version/revision, dates and provider availability when comparing runs. Live reports do not
apply the local policy version to a remote server. Provider timings for deployed new code
are in server logs; black-box client latency does not reveal their breakdown.

Forecast verification is separate:

```bash
uv run python -m evaluations.forecast_verification --pairs "$TASK_DIR/work/pairs.json" --out-dir "$TASK_DIR/out/verification"
```

Each pair supplies `site_id`, timezone-aware `valid_time`, a `forecast` with `source`,
`issued_at`, `effective_cloud_percent` and/or `precipitation_probability` (0–1), and an
`observation` with matching `site_id`/`valid_time`, `source`, `kind: "observation"`,
`effective_cloud_percent` and/or boolean `precipitation_occurred`. Clouds must use comparable
measurement definitions. The verifier reports cloud MAE in percentage points, rain Brier
score, sample counts, lead times and rejected pairs; an empty set earns no accuracy result.
Source labels are a necessary audit trail, not independent proof of observation quality.
Ground observations or a clearly identified independent reference must be retained before
claiming real forecast skill. No recurring automation or production deployment is created.

### Prospective capture and observation pairing

`forecast_archive.py` captures the existing weather capability for an explicitly supplied WGS84
point. Every invocation writes a separate archive containing normalized provider results and
retrieval start/completion timestamps; it never overwrites an earlier capture. Choose the actual
observation station coordinates after checking the source's station metadata. A nearby station
does not validate a different observing site. Example coordinates below are synthetic test inputs.

```bash
uv run python -m evaluations.forecast_archive capture --site-id test-site --lat 30 --lon 120 --timezone Asia/Shanghai --out-dir "$TASK_DIR/out/captures"
uv run python -m evaluations.forecast_archive pair --archives "$TASK_DIR"/out/captures/forecast-*.json --observations "$TASK_DIR/work/observations.json" --out-dir "$TASK_DIR/out/verification"
```

The observation file is a JSON array. The following is a **synthetic format example**, not a
measurement or a validated reference source:

```json
[
  {
    "site_id": "test-site",
    "lat": 30,
    "lon": 120,
    "valid_time": "2026-11-02T12:00:00Z",
    "source": "independent-station",
    "kind": "observation",
    "cloud_definition": "max_total_and_layers_percent",
    "effective_cloud_percent": 40,
    "precipitation_definition": "preceding_hour_total_precipitation_gt_0.1mm",
    "precipitation_occurred": false
  }
]
```

Pairing requires exact site, coordinates and UTC time, with no nearest-station or nearest-hour
substitution. Duplicate observation identities are ambiguous and excluded; repeating the same
archive cannot multiply samples. Forecast hours at/before completed retrieval are excluded.
Cloud comparisons require the same maximum-of-total-and-layer definition; total cloud oktas alone
do not establish it. Invalid or absent fields remain unknown. Open-Meteo precipitation probability
refers to **more than 0.1 mm during the preceding hour**, per its
[official variable definitions](https://open-meteo.com/en/docs#hourly-parameter-definition).
Rain comparisons require that exact event definition and capture before the full event period;
point-in-time rain reports do not qualify. Other providers' rain periods are not yet reviewed,
so their precipitation probabilities are not scored by the archive pairer.

The pairer writes `forecast-pairs.json` for the existing verifier and `forecast-pairing.json`
with unmatched/excluded/rejected records and verification metrics. No matching observations means
no accuracy result and a nonzero command exit. Model issue time stays `null`; `available_at`
records completed retrieval, and `lead_time_basis` distinguishes that conservative availability
bound from a supplied actual `issued_at`. Multiple retrievals may verify against the same
observation; their errors are correlated and must not be called independent weather events.
Source labels and matching metadata are an audit trail, not proof of source independence or quality.
An observation adapter still requires separate review of definitions, station metadata and licensing.
No independent observation feed or recurring capture schedule is installed by these commands.

See [the independent-source review](../docs/forecast-observation-sources.md) before building an
observation adapter. Legacy NCEI ISD is retired; its current replacement is GHCNh. A source's
nominal hourly labels, cloud categories and missing rainfall require source-specific review
before they can qualify as verification observations.
