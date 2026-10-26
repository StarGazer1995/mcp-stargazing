# mcp-stargazing

Calculate the altitude, rise, and set times of celestial objects (Sun, Moon, planets, stars, and deep-space objects) for any location on Earth, with optional light pollution analysis.

## Features

- **Altitude/Azimuth Calculation**: Get elevation and compass direction for any celestial object.
- **Rise/Set Times**: Determine when objects appear/disappear above the horizon.
- **Light Pollution Analysis**: Load and analyze light pollution maps (GeoTIFF format).
- **Composite Planning**: Build a ranked observing plan that combines place quality, weather, moonlight, and top targets.
- **Tool Discovery**: Inspect registered MCP tools programmatically through `get_tool_catalog`.
- **Code Execution Ready**:
  - **Serializable Returns**: All tools return JSON-serializable data (ISO strings for dates), making them directly usable by LLMs.
  - **Pagination**: `analysis_area` supports paging (`page`, `page_size`) to handle large datasets efficiently.
  - **Stable Result Handles**: `analysis_area.resource_id` identifies the cached non-pagination query so agents can fetch multiple pages safely.
  - **Standardized Responses**: Successful calls return `{ "data": ..., "_meta": ... }`; business validation failures return `{ "error": ..., "_meta": ... }`.
- **Performance**:
  - **Async Execution**: Non-blocking celestial calculations.
  - **Caching**: Intelligent caching for Simbad queries and regional analysis.
  - **Proxy Support**: Native support for HTTP/HTTPS proxies (useful for downloading astronomical data).
- **Time Zone Aware**: Works with local or UTC times.
- **Data Driven**: Integrated database of 10,000+ deep-sky objects (Messier & NGC) for smart recommendations.

## Installation

This project uses [uv](https://github.com/astral-sh/uv) for dependency management.

### Local Installation

1. **Install `uv`**:
   ```bash
   pip install uv
   ```

2. **Sync dependencies**:
   ```bash
   uv sync
   ```
   This will create a virtual environment in `.venv` and install all dependencies defined in `pyproject.toml`.

3. **Activate the environment**:
   ```bash
   source .venv/bin/activate
   ```

4. **Initialize Data** (Required for Nightly Planner):
   This downloads the latest Messier and NGC catalog data to `src/data/objects.json`.
   ```bash
   python scripts/download_data.py
   ```
   *Note: If you are behind a firewall, ensure `HTTP_PROXY` env var is set before running this script.*

### Docker Installation

You can also run the server using Docker, which handles all dependencies and data initialization automatically.

1. **Build the image**:
   ```bash
   docker build -t mcp-stargazing .
   ```
   
   *Note: If you are behind a proxy, pass the proxy URL during build:*
   ```bash
   docker build --build-arg HTTP_PROXY=http://127.0.0.1:7890 -t mcp-stargazing .
   ```

2. **Run the container**:
   ```bash
   # Basic run (MCP on :3001 + SPF web UI on :5001)
   docker run -p 3001:3001 -p 5001:5001 mcp-stargazing
   
   # With Environment Variables
   docker run -p 3001:3001 -p 5001:5001 \
     -e QWEATHER_API_KEY=your_key \
     -e STARGAZING_DB_CONFIG=your_db_config \
     mcp-stargazing
   ```

3. **Access**:
   - **MCP server** → `http://localhost:3001/shttp` (for AI agent / MCP client)
   - **SPF web UI** → `http://localhost:5001/` (stargazing place finder frontend)

### Docker Architecture

The container runs two services managed by [supervisord](http://supervisord.org/), both sharing the same Python
virtual environment via `uv run`:

```
Container
├── supervisord
│   ├── program:mcp      → uv run mcp-stargazing --mode shttp --port 3001
│   └── program:spf-web  → uv run uvicorn server.main:app --port 5001
│
Dependency resolution (single venv, no duplication):
  stargazing-core>=0.2.0  ←  resolved once from PyPI
  stargazing-place-finder>=0.9.1
  fastapi, uvicorn, ...   ←  SPF's transitive deps
```

## MCP Server Usage

Start the MCP server to expose tools to AI agents or other clients.

### Agent-first direction

`plan_stargazing_session` is the preferred composite decision entry point for third-party agents.
It accepts a place name, center/radius, or exact bounds; resolves Seestar S50,
HOPE D60 + ASI2600MC Air, or custom optics configurations; keeps provider and database choices on
the server; and returns a first-class decision, alternatives, exact score components, evidence,
uncertainties, material missing inputs, ranking-reversal conditions, and next actions.

`get_best_stargazing_plan` and `get_multiday_stargazing_plan` remain registered as compatibility
entries for existing bbox-first callers. The deterministic 10-scenario gate and representative
Codex/Claude black-box smoke passed before the primary entry point was registered. New independent
astronomy lookup tools remain deferred while long-running task semantics and the 1.0 contract are
completed.

See [Third-party Agent Contract](docs/agent-contract.md),
[Workspace Technical Map](docs/workspace-technical-map.md), and
[Agent Evolution Checklist](docs/workspace-action-checklist.md). The current 17-tool routing and
parameter review is recorded in [Tool Surface Audit](docs/tool-surface-audit.md). Evaluation assets
and the two-client evidence are under [`evaluations/`](evaluations/README.md).

### 1. Environment Setup

Create a `.env` file or export variables:

```bash
# Weather tools
# 推荐：使用你账号专属的 API Host（公共域名将从 2026 年起逐步停止服务）
export QWEATHER_API_HOST="abc1234xyz.def.qweatherapi.com"

# 鉴权（二选一）
# 1) API KEY（兼容旧用法）
export QWEATHER_API_KEY="your_api_key"
# 2) JWT（推荐，更安全）
# export QWEATHER_JWT_TOKEN="your_jwt_token"

# 如需临时兼容旧公共域名（不推荐），显式开启：
# export QWEATHER_ALLOW_PUBLIC_HOST=1

# Geocoding（默认零付费、零 key）
# CJK 查询默认使用内置离线行政区划数据；未命中时回退 Photon / Nominatim。
# 可选 provider 顺序覆盖（全部支持：gazetteer, photon, nominatim, amap）
# export GEOCODER_PROVIDERS="gazetteer,photon,nominatim"

# 仅当你希望显式启用付费的 Amap 地理编码时才需要：
# export GEOCODER_PROVIDERS="amap,gazetteer,photon,nominatim"
# export AMAP_KEY="your_amap_key"

# Optional: Proxy for downloading astronomical data (Simbad/IERS)
# Highly recommended if you are in a restricted network environment
export HTTP_PROXY="http://127.0.0.1:7890"
export HTTPS_PROXY="http://127.0.0.1:7890"
```

### 2. Start Server

**Streamable HTTP (SHTTP) mode** (Recommended for most agents):

```bash
# Basic start
python -m src.main --mode shttp --port 3001 --path /shttp

# With proxy explicitly passed (overrides env vars)
python -m src.main --mode shttp --port 3001 --path /shttp --proxy http://127.0.0.1:7890
```

**SSE mode**:

```bash
python -m src.main --mode sse --port 3001 --path /sse
```

`dev` mode is no longer supported because current FastMCP versions no longer provide `run_dev()`. Use `local`, `shttp`, or `sse`.

### 3. Response Format

Successful business responses return data in a standardized JSON format:

```json
{
  "data": {
    // Tool-specific return data
    "altitude": 45.5,
    "azimuth": 180.0
  },
  "_meta": {
    "version": "1.0.0",
    "status": "success"
  }
}
```

Business validation failures use the same envelope style:

```json
{
  "error": {
    "code": "INVALID_TIME_FORMAT",
    "message": "Invalid time format: invalid-time-format",
    "details": {
      "time_string": "invalid-time-format"
    }
  },
  "_meta": {
    "version": "1.0.0",
    "status": "error"
  }
}
```

At the MCP protocol layer, `tools/list` and `get_tool_catalog` are kept aligned, and JSON-RPC request ids are preserved in both SHTTP and SSE transport tests.

### 4. Available Tools

- **`get_celestial_pos`**: Calculate altitude/azimuth.
- **`get_celestial_rise_set`**: Calculate rise/set times (Returns ISO strings). Use `event_scope="calendar_day"` for the historical full-local-day behavior, or `event_scope="next_events"` to find the first rise and first set after the supplied `time`, rolling across midnight when needed.
- **`get_moon_info`**: Detailed moon phase, illumination, and age.
- **`list_visible_planets`**: List of all planets currently above the horizon with positions.
- **`get_constellation`**: Find the position (Alt/Az) of a constellation center.
- **`get_nightly_forecast`**: Smart planner returning curated list of best objects to view tonight (Planets + Deep Sky) plus the local civil-dark `night_window` with dusk, dawn, duration, date, and timezone.
- **`get_weather_by_name` / `get_weather_by_position`**: Fetch current weather with automatic retry on network failures.
- **`get_local_datetime_info`**: Get current local time information.
- **`get_tool_catalog`**: Discover available MCP tool metadata and parameters.
- **`plan_stargazing_session`**: Preferred end-to-end entry point for deciding when, where, and what to observe across one to seven nights.
  - **Inputs**: a `request` object containing `location` (exactly one of `place_name`, `center`, or `bounds`), `start_date`, optional `time_zone`, `nights`, `observation_style`, `equipment`, candidate/target limits, and popularity preferences.
  - **Equipment**: stable presets are `seestar_s50` and `hope_d60_asi2600mc_air`; advanced callers may use `custom` or override individual optical fields.
  - **Returns**: normalized request and resolved geography, a first-choice `decision`, ranked `alternatives`, traceable `evidence`, `uncertainties`, material `missing_inputs`, `would_change_if` conditions, and concrete `next_actions`.
  - **Routing**: use this for a complete observing decision. Use weather, celestial, telescope, or place tools directly for focused fact lookups.
- **`get_best_stargazing_plan`**: Build a ranked regional observing plan with candidate places, weather summaries, best observation windows, and top targets.
  - **Inputs**: `south`, `west`, `north`, `east`, `time`, `time_zone`, `candidate_limit`, `target_limit`, `weather_provider`, `max_locations`, `min_height_diff`, `road_radius_km`, `network_type`, `observation_style`, `avoid_popular_spots`, `prefer_quiet_at_night`, `popularity_radius_km`, `db_config_path`.
  - **Candidate recall**: `candidate_limit` is the number of ranked candidates returned. The service evaluates a bounded recall pool before final truncation, so a location with better weather can overtake a statically higher-ranked location.
  - **Cost-aware evaluation**: the recall pool receives a low-cost weather screen first; night-window and target-forecast evaluation then runs only for the strongest internal candidates before the final ranking.
  - **Regional weather signal**: when available, the server samples the stargazing-core spatial cloud-cover grid once for the whole bbox and blends it into regional comparison; a spatial-model failure degrades without failing the plan.
  - **Returns**: `query`, `summary`, and `candidates`, where `query.analysis_resource_id` links the plan back to the underlying neutral `analysis_area` search when available. When popularity preferences are enabled, MCP applies a single adjustment from the returned heuristic fields, surfaces those reasons in `candidates[*].recommendation_reasons`, and summarizes the top recommendation in `summary.popularity_preferences_enabled`, `summary.primary_recommendation_drivers`, and `summary.recommended_location_reason_summary`. Each candidate's `score_breakdown.factor_contributions` exposes the signed place, weather, popularity, and accessibility contributions used for ranking; explanatory reasons use the same active factors. The driver values form a stable enum: `dark_sky`, `high_place_score`, `clear_weather`, `good_visibility`, `observation_style_fit`, `low_popularity_risk`, `quiet_at_night`, and `strong_targets`.
  - **Popularity ownership**: all composite planners (single-night, multi-night, and `plan_stargazing_session`) request SPF place scores with `avoid_popular_spots=false` and `prefer_quiet_at_night=false`, preserving `popularity_radius_km` and the heuristic evidence. MCP alone applies the requested preferences; screening and final evaluation each start from the neutral score. Request echoes retain the user's preferences. To reproduce `query.analysis_resource_id` (or the primary planner's place `evidence.resource_id`), repeat the same area search with both preference flags disabled. Standalone `analysis_area` still forwards preferences to SPF and uses a separate cache entry when enabled.
  - **Observation style**: `balanced` preserves the default behavior. `deep_sky` emphasizes dark skies and low moonlight, `visual` raises the weather weight, `planetary` reduces moon penalties and prioritizes planets, and `beginner` also favors nearby road access.
  - **Night window**: each candidate includes `night_window` when civil darkness can be determined, with local date, civil dusk, following civil dawn, duration, and timezone. `best_observation_window` now represents a continuous dark-sky run when hourly data permits; `start_time`, weather fields, and the additive `end_time`, `duration_hours`, and `quality_score` are returned together.
- **`get_multiday_stargazing_plan`**: Compare one to seven consecutive nights and return the best night and location across the region.
  - **Inputs**: `south`, `west`, `north`, `east`, `start_date`, `time_zone`, `nights`, plus the same candidate, weather, street-network, and observation-style options as `get_best_stargazing_plan`.
  - **Returns**: `query`, a cross-night `summary` with `best_night_date`, `best_location_name`, and `best_score`, and `nights[]` where each night contains its `night_window`, nightly `plan`, errors, and warnings.
  - **Degradation**: Weather or forecast sub-queries may degrade into `summary.warnings` and per-candidate `notes`, while the overall planning response remains successful.
- **`get_telescope_targets`**: Match deep-sky objects against telescope optics — find what's best visible with your equipment.
  - **Inputs**: `focal_length_mm`, `lon`, `lat`, `time`, `time_zone`, plus optional optics fields such as `aperture_mm`, sensor dimensions, pixel size, reducer/Barlow factor, mount type, filter, and `limit`.
  - **Returns**: Ranked targets with visibility scores, altitude/azimuth, rise/set/transit data, FOV fit, surface brightness, mosaic guidance, and the normalized telescope configuration.
- **`get_shooting_plan`**: Generate an optimized imaging schedule for a target, maximizing time above altitude threshold.
  - **Inputs**: the same telescope/observer fields as `get_telescope_targets`, plus optional `limit` and `min_altitude`.
  - **Returns**: `targets`, `moon`, a single-night `plan` with timed imaging slots, `config`, and `total`.
- **`light_pollution_map`**: Query light pollution data for a bounding box area.
  - **Inputs**: `south`, `west`, `north`, `east`, `zoom` (default 10).
  - **Returns**: A grid of data points with Bortle class, brightness, and SQM values.
- **`analysis_area`**: Find best stargazing spots in a region.
  - **Inputs**: `south`, `west`, `north`, `east`, `max_locations`, `min_height_diff`, `road_radius_km`, `network_type`, `avoid_popular_spots`, `prefer_quiet_at_night`, `popularity_radius_km`, `db_config_path`, `page`, `page_size`.
  - **Returns**: List of spots with pagination metadata (`total`, `page`, `page_size`, `total_pages`) and a `resource_id` that identifies the cached non-pagination query parameters. Each item may also include popularity heuristic fields such as `static_popularity_risk_score`, `night_quiet_likelihood_score`, and `popularity_notes`.
  - **Validation**: `page >= 1`, `page_size >= 1`, and `popularity_radius_km > 0`; invalid arguments return `CONFIGURATION_ERROR`.

### 5. Error Handling

All tools return JSON-serializable data and use structured error handling:

- **Standard Error Codes**: `INVALID_COORDINATES`, `INVALID_TIMEZONE`, `INVALID_TIME_FORMAT`, `MISSING_API_KEY`, `API_AUTH_FAILURE`, `API_TIMEOUT`, `API_RATE_LIMIT`, `EXTERNAL_API_ERROR`, `NETWORK_ERROR`, `CONFIGURATION_ERROR`
- **Weather Tools**: Include automatic retry logic for network failures (up to 3 attempts with exponential backoff)
- **Business Error Responses**: Structured MCPError-derived payloads with actionable messages for calling agents
- **Protocol Tests**: `tools/list`, `get_tool_catalog`, and SSE request-id behavior are covered by protocol-level tests
- **Validation**: Input parameters are validated before processing with clear error messages

## Examples

- **Nightly Planner**: `python examples/nightly_forecast_demo.py`
  - Shows a curated list of planets and deep-sky objects visible tonight, accounting for moonlight.

- **Visible Planets**: `python examples/visible_planets_demo.py`
  - Lists which planets are currently up.

- **Moon Info**: `python examples/moon_phase_demo.py`
  - Prints a 30-day moon phase calendar.

- **Orchestration**: `python examples/code_execution_orchestration.py`
  - Demonstrates a full workflow: Get time -> Get Celestial Pos -> Check Weather -> Find Spots.
  - Shows how to handle the standardized response format programmatically.

- **Pagination**: `python examples/pagination_demo.py`
  - Demonstrates fetching large result sets page by page using the `resource_id`.

- **Telescope Targets**: `python examples/telescope_targets_demo.py`
  - Ranks deep-sky targets for a RedCat51-style optical configuration.

- **Shooting Plan**: `python examples/shooting_plan_demo.py`
  - Produces a time-ordered single-night imaging plan.

## Project Structure

```
.
├── src/
│   ├── functions/            # Tool implementations grouped by domain
│   │   ├── celestial/        # Celestial calculations (pos, rise/set)
│   │   ├── metadata/         # Tool discovery surface (`get_tool_catalog`)
│   │   ├── planning/         # Single-night and multi-night composite planning
│   │   ├── telescope/        # Telescope target matching + shooting plan
│   │   ├── weather/          # Weather API integration
│   │   ├── places/           # Location and area analysis
│   │   └── time/             # Time utilities
│   ├── services/             # Transport-independent application services
│   │   └── planning.py       # Single-night and multi-night planning orchestration
│   ├── schemas/              # Pydantic v2 data models
│   ├── analysis_cache.py     # Caching logic for analysis results
│   ├── response.py           # Standardized response formatting
│   ├── server_instance.py    # FastMCP server instance (avoids circular imports)
│   ├── main.py               # Entry point and tool registration
│   ├── celestial.py          # Core astronomy logic (Astropy wrappers)
│   ├── placefinder.py        # Place-finder bridge logic
│   └── qweather_interaction.py # Thin QWeather URL wrappers
├── tests/                    # Unified test suite covering every registered tool
├── examples/                 # Runnable usage examples, including both telescope tools
├── docs/                     # Design docs and roadmap
├── Dockerfile                # Multi-stage Docker build
├── supervisord.conf          # Dual-service process manager config
└── pyproject.toml            # Project configuration and dependencies
```

## Testing

Run the unified test suite:

```bash
uv run pytest -v tests/
```

Key tests include:
- `test_serialization.py`: Ensures all tools return valid JSON with the correct schema.
- `test_integration.py`: Mocks external APIs to verify the entire toolchain.
- `test_mcp_client.py`: Verifies `tools/list`, `tools/call`, and SSE request-id protocol behavior.
- `test_structured_errors.py`: Verifies business validation failures stay in the structured response envelope.

Cross-repository compatibility is checked by the reusable
[dependency-chain workflow](docs/dependency-chain-ci.md). It tests
`stargazing-core → stargazing-place-finder → mcp-stargazing` using baseline and
candidate wheels, and blocks changes that add downstream failures.

## Contributing

1.  Follow the [Code Execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp) best practices.
2.  Ensure all new tools return standard JSON responses using `src.response.format_response`.
3.  Add tests in `tests/` for any new functionality.
4.  Follow the repository agent conventions in `AGENTS.md` for all MCP tool and agent-facing changes.
5.  Refer to `docs/agent-contract.md` and `docs/ROADMAP.md` for the public agent direction and
    implementation roadmap.
