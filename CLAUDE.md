# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

See also `AGENTS.md` for broader agent guidance including tool registration conventions, error handling rules, and CI/CD details.

## Package Management

**Always use `uv`** — never `pip`, `pip3`, or `python -m pip`. `uv` is the project's package manager and all commands (install, test, lint, run) use it.

- Use `uv sync` / `uv add` / `uv remove` for dependencies
- Use `uv run <command>` to run any script or CLI within the project venv
- Use `uv --directory <path> run <command>` when working from a different project's directory
- For the SPF project (`stargazing-place-finder`), same rules apply — it also uses `uv`

## Quick Commands

| Action | Command |
|--------|---------|
| Install deps | `uv sync` |
| Run all tests | `uv run pytest -v tests/` |
| Run single test file | `uv run pytest tests/test_<name>.py` |
| Lint + format check | `uv run ruff format --check src/ tests/ && uv run ruff check src/ tests/` |
| Security scan | `uv run bandit -r src/ -c pyproject.toml --severity-level medium` |
| Start server (SHTTP) | `uv run python -m src.main --mode shttp --port 3001 --path /shttp` |
| Start server (SSE) | `uv run python -m src.main --mode sse --port 3001 --path /sse` |
| Start server (local) | `uv run python -m src.main --mode local` |
| Download astro data | `uv run python scripts/download_data.py` |
| Build Docker image | `docker build -t mcp-stargazing .` |

## Architecture

```
MCP Transport Layer:   Streamable HTTP (:3001)  |  SSE  |  Local (stdio)
                                |
                     FastMCP (server_instance.py)
                     Custom MCP wrapper with _tool_metadata registry
                                |
              ┌─────────────────┼─────────────────┐
              |                 |                  |
        Tool Layer        Core Layer          Schema Layer
   src/functions/*/    src/*.py              src/schemas/*.py
   impl.py (6 domains) celestial.py          Pydantic v2 BaseModel
              |         placefinder.py       (10 model files)
              |         response.py
              |         cache.py
              |         retry.py
              |         utils.py
              └─────────────────┼──────────────────┘
                                |
                     External Dependencies
            Astropy  |  stargazing-place-finder  |  Weather APIs
```

**Tool domains** (each in `src/functions/<domain>/impl.py`):
- **celestial** — 6 async tools: positions, rise/set, moon, planets, constellation, nightly forecast
- **weather** — 2 sync tools (with retry): weather by name, weather by position. Multi-provider aggregation.
- **places** — 2 async tools: light pollution map, analysis area (paginated + cached)
- **planning** — 1 async tool: composite best-stargazing-plan (places + weather + forecast)
- **time** — 1 sync tool: local datetime info
- **metadata** — 1 sync tool: tool catalog discovery

**Data flow**: MCP client → `main.py` (registers all tool modules via import) → `@mcp.tool()` decorators → `functions/*/impl.py` → core layer → external services. All responses pass through `response.py` envelope (`{data, _meta}` or `{error, _meta}`).

## Key Source Layout

```
src/
├── main.py                  # Entry point: CLI args, IERS config, proxy, mode dispatch
├── server_instance.py       # Custom MCP wrapper around FastMCP with _tool_metadata registry
├── response.py              # format_response(), format_error(), MCPError (10 error codes)
├── celestial.py             # Core astronomy: AltAz, rise/set, moon phase, planets, SIMBAD
├── placefinder.py           # Bridge to stargazing-place-finder package (SPF)
├── cache.py                 # AnalysisCache: TTL-based in-memory cache for analysis_area results
├── retry.py                 # retry_on_failure decorator (async + sync, exponential backoff)
├── utils.py                 # Coordinate validation, time parsing, timezone normalization
├── paths.py                 # sys.path management for SPF import resolution
├── qweather_interaction.py  # QWeather API client (JWT + API-KEY auth, URL building)
│
├── schemas/                 # Pydantic v2 data models
│   ├── base.py              # GeoPoint, GeoBounds, TimeInfo, ProviderType
│   ├── celestial.py         # CelestialPosition, RiseSet, MoonInfo, VisiblePlanet, etc.
│   ├── weather.py           # CurrentWeather, ProviderResult, AggregatedWeatherResponse
│   ├── places.py            # LightPollutionGrid, StargazingLocation, AnalysisAreaResult
│   ├── planning.py          # PlanningQuery, ObservationWindow, BestStargazingPlan
│   ├── pagination.py        # Generic PaginatedResult[T]
│   └── error.py             # ErrorCode StrEnum
│
├── data/
│   ├── objects.json         # 10,000+ Messier/NGC deep-sky objects
│   └── constellation_centers.json
│
├── functions/
│   ├── celestial/impl.py    # 6 tools: pos, rise/set, moon, planets, constellation, forecast
│   ├── metadata/impl.py     # get_tool_catalog
│   ├── places/impl.py       # light_pollution_map, analysis_area (paginated)
│   ├── planning/impl.py     # get_best_stargazing_plan (composite)
│   ├── time/impl.py         # get_local_datetime_info
│   └── weather/
│       ├── impl.py          # get_weather_by_name, get_weather_by_position (with retry)
│       ├── service.py       # Multi-provider aggregation (open-meteo > qweather > wttr)
│       ├── geocoding.py     # Cascading geocoder: Amap → Photon → Nominatim
│       ├── models.py        # Backward-compat re-exports of weather schemas
│       └── providers/
│           ├── open_meteo.py
│           ├── qweather.py
│           └── wttr.py
│
├── tests/                   # 21 test files (pytest + pytest-asyncio)
├── examples/                # 14 example/demo scripts
├── docs/                    # Design docs and ROADMAP.md
└── scripts/download_data.py # Messier/NGC catalog downloader
```

## Critical Design Patterns

1. **Response envelope** — All tools must return `format_response(data)` or `format_error(code, msg)`. Never return raw dicts. The `_meta` wrapper carries `version` and `status` on every response.

2. **Tool registration by import** — `main.py` imports all `functions/*/impl.py` modules at startup. Each module's `@mcp.tool()` decorators register tools on the `MCP` singleton. No explicit tool list — import side effects drive registration.

3. **MCPError for business errors** — Validation failures are raised as `MCPError(code, message, details)` and caught centrally by `_respond_with_mcp_error()` wrappers in tool `impl.py` files. Raw exceptions must not escape tool functions.

4. **Async wrapping for blocking I/O** — Astronomy (Astropy) and place-finder (SPF) calls are synchronous. Tools wrap them in `asyncio.to_thread()` to avoid blocking the event loop. Weather tools are sync but wrapped with `retry_on_failure`.

5. **Multi-provider aggregation with degradation** — Weather queries cascade: open-meteo → qweather → wttr. Partial provider failures become notes/warnings in the response rather than failing the entire request. Geocoding cascades similarly: Amap → Photon → Nominatim.

6. **Place-finder bridge** — `StargazingPlaceFinder` in `placefinder.py` wraps the `stargazing-place-finder` package's public API. Uses `sys.path` manipulation via `paths.py` to ensure SPF's internal imports resolve correctly. Avoids re-initializing the SPF singleton when parameters haven't changed (compares `_last_params` dict), preventing repeated GeoTIFF open and PostGIS pool creation.

7. **Pagination with stable resource_id** — `analysis_area` returns `resource_id` keyed on non-pagination query params (MD5 of sorted kwargs). Cache TTL is 3600s. Cache key excludes `page` and `page_size`, so paginating through results hits the same cache entry.

8. **Retry with exponential backoff** — `retry_on_failure` supports both sync and async functions. Default: 3 attempts, 1s base delay, 30s max, 2x backoff. Used by weather tools for transient network errors.

## Testing

- Config in `pyproject.toml`: `pythonpath = ["src"]`, `testpaths = ["tests"]`
- 21 test files covering: celestial, weather, places, planning, serialization, MCP protocol, tool metadata, structured errors, integration
- `test_mcp_client.py` — MCP protocol tests (tools/list, tools/call, SSE request-id)
- `test_serialization.py` — Every tool's response validates against expected JSON schema
- `test_structured_errors.py` — Business error payload normalization
- `test_tool_metadata.py` — Tool metadata registry vs tools/list alignment
- CI enforces **100% diff-cover** on PRs
- Tests run inside Docker in CI; FastMCP stub available in `server_instance.py` for test environments

## Known Sharp Edges

### Real issues (verified 2026-06-28)

- **Place-finder bridge uses `sys.path` manipulation** (`paths.py`) — inserts SPF's source root into `sys.path` at import time to resolve SPF's internal cross-module imports. Fragile: breaks if SPF's package structure changes or if a same-named module from another dependency shadows it. Long-term fix: SPF should expose a clean public API that doesn't require source-root path hacks.
- **Global module-level caches are not thread-safe** — `AnalysisCache` (`cache.py`), `OBJECTS_CACHE`, and `CONSTELLATIONS_CACHE` (both in `celestial.py`) use plain `dict` without locks. Multiple asyncio tasks concurrently reading/writing could cause data races. The GIL mitigates bytecode-level corruption but not logical races (e.g., cache stampede on miss).
- **Weather provider code is repetitive** — `open_meteo.py`, `qweather.py`, and `wttr.py` follow nearly identical fetch → parse → normalize → return patterns. A shared abstract base class or Protocol would eliminate ~60% duplication. Adding a fourth provider currently means copy-pasting one of the three.
- **`qweather_interaction.py` mixes concerns** — handles JWT generation, API-KEY auth, URL building, HTTP fetching, and error translation in a single module. Split into auth, HTTP client, and error mapping layers.
- **No observability** — no structured logging, no metrics, no tracing. The only output is `print()` in `main.py`. Hard to monitor in production or debug transient failures.
- **Python 3.13+ only** — limits deployment options. Many cloud platforms and Docker base images still default to 3.12. The core dependency `stargazing-place-finder` supports 3.9–3.12, creating a version mismatch between the two projects.

### Notes

- **`server_instance.py` has a FastMCP fallback stub** — for test environments without the real `fastmcp` package. The stub is minimal and doesn't actually serve requests; it only exists so that tool registration and metadata tests can import `mcp` without a real server.
- **IERS auto-download is opt-in** — set `ASTROPY_IERS_AUTO_DOWNLOAD=1` to allow Astropy to fetch updated Earth orientation parameters. Off by default because it requires network access and can hang behind firewalls.

## Commit Policy

- **Never commit internal planning documents** — code review findings, implementation plans, design drafts, or meeting notes stay local or in `.claude/plans/`. Only commit source code, docs, and config that are intended for the public repo.
- Use `git status` to verify only expected files are staged before committing.

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `QWEATHER_API_HOST` | QWeather API host (recommended: account-specific host) |
| `QWEATHER_API_KEY` | QWeather API key (legacy auth) |
| `QWEATHER_JWT_TOKEN` | QWeather JWT token (preferred auth) |
| `QWEATHER_ALLOW_PUBLIC_HOST` | Set to `1` to use legacy public API host (deprecated) |
| `AMAP_KEY` | Amap (高德) API key for CJK geocoding |
| `HTTP_PROXY` / `HTTPS_PROXY` | Proxy for Astropy IERS/SIMBAD downloads |
| `MCP_HOST` | Server bind address (default `0.0.0.0`) |
| `ASTROPY_IERS_AUTO_DOWNLOAD` | Set to `1` to enable IERS auto-download |
| `STARGAZING_CONFIG` | Path to SPF TOML config (forwarded to place-finder bridge) |
| `STARGAZING_DB_CONFIG` | Path to PostGIS config (forwarded to place-finder bridge) |

## Release Process

1. Branch `release/vX.Y.Z`, bump version in `pyproject.toml`
2. PR → review → merge to `main`
3. `git checkout main && git fetch origin && git reset --hard origin/main`
4. `git tag vX.Y.Z && git push origin vX.Y.Z`
5. CI auto-publishes to PyPI (OIDC Trusted Publishing) and builds Docker image to GHCR
6. **Never** force-push or re-push the same tag.
