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
| Run Docker (dual-service) | `docker run -p 3001:3001 -p 5001:5001 mcp-stargazing` |

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
              |    analysis_cache.py
              |         retry.py
              |         utils.py
              └─────────────────┼──────────────────┘
                                |
                     External Dependencies
            Astropy  |  stargazing-place-finder  |  Weather APIs
```

**Tool domains** (each in `src/functions/<domain>/impl.py`):
- **celestial** — 6 async tools: positions, rise/set, moon, planets, constellation, nightly forecast
- **telescope** — 2 async tools: target matching for telescope optics, shooting plan generation
- **weather** — 2 sync tools (with retry): weather by name, weather by position. Multi-provider aggregation.
- **places** — 2 async tools: light pollution map, analysis area (paginated + cached)
- **planning** — 2 async tools: single-night and multi-night composite planning
- **time** — 1 sync tool: local datetime info
- **metadata** — 1 sync tool: tool catalog discovery

**Data flow**: MCP client → `main.py` (registers all tool modules via import) → `@mcp.tool()` decorators → `functions/*/impl.py` → application/core layer → external services. Planning wrappers delegate validation, orchestration, ranking, and explanation to `services/planning.py`, which consumes transport-free place, weather, forecast, and night-window capabilities rather than another tool's `.fn`. All public responses pass through `response.py` envelope (`{data, _meta}` or `{error, _meta}`).

## Key Source Layout

```
src/
├── main.py                  # Entry point: CLI args, IERS config, proxy, mode dispatch
├── server_instance.py       # Custom MCP wrapper around FastMCP with _tool_metadata registry
├── response.py              # format_response(), format_error(), MCPError (10 error codes)
├── celestial.py             # Core astronomy: AltAz, rise/set, moon phase, planets, SIMBAD
├── placefinder.py           # Bridge to stargazing-place-finder package (SPF)
├── analysis_cache.py        # AnalysisCache: TTL-based in-memory cache for analysis_area results
├── retry.py                 # retry_on_failure decorator (async + sync, exponential backoff)
├── utils.py                 # Coordinate validation, time parsing, timezone normalization
├── paths.py                 # Repository path constants
├── logging_config.py        # Structured logging (structlog) with request-id context
├── qweather_interaction.py  # QWeather API client (JWT + API-KEY auth, URL building)
│
├── services/
│   └── planning.py          # Transport-independent single/multi-night application service
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
│   ├── telescope/impl.py    # 2 tools: get_telescope_targets, get_shooting_plan
│   ├── metadata/impl.py     # get_tool_catalog
│   ├── places/impl.py       # light_pollution_map, analysis_area (paginated)
│   ├── planning/impl.py     # Thin MCP adapters for composite planning
│   ├── time/impl.py         # get_local_datetime_info
│   └── weather/
│       ├── impl.py          # get_weather_by_name, get_weather_by_position (with retry)
│       ├── service.py       # Multi-provider aggregation (open-meteo > qweather > wttr)
│       ├── geocoding.py     # Cascading geocoder: gazetteer → Photon → Nominatim (Amap opt-in)
│       ├── gazetteer.py     # Offline China province/city/district gazetteer
│       ├── models.py        # Backward-compat re-exports of weather schemas
│       └── providers/
│           ├── open_meteo.py
│           ├── qweather.py
│           └── wttr.py
│
├── tests/                   # Full pytest/pytest-asyncio harness for all 17 tools
├── examples/                # Runnable demos, including both telescope tools
├── docs/                    # Design docs and ROADMAP.md
├── Dockerfile               # Multi-stage build (test + production)
├── supervisord.conf          # Dual-service process manager (MCP + SPF web)
└── scripts/download_data.py # Messier/NGC catalog downloader
```

## Critical Design Patterns

1. **Response envelope** — All tools must return `format_response(data)` or `format_error(code, msg)`. Never return raw dicts. The `_meta` wrapper carries `version` and `status` on every response.
2. **Internal capability boundary** — Cross-domain application services call undecorated capability functions that return Pydantic models or raise `MCPError`; they never chain FastMCP wrapper `.fn` hooks. Public wrappers alone add the response envelope.

3. **Tool registration by import** — `main.py` imports all `functions/*/impl.py` modules at startup. Each module's `@mcp.tool()` decorators register tools on the `MCP` singleton. No explicit tool list — import side effects drive registration.

4. **MCPError for business errors** — Validation failures are raised as `MCPError(code, message, details)` and caught centrally by `_respond_with_mcp_error()` wrappers in tool `impl.py` files. Raw exceptions must not escape tool functions.

5. **Async wrapping for blocking I/O** — Astronomy (Astropy) and place-finder (SPF) calls are synchronous. Tools wrap them in `asyncio.to_thread()` to avoid blocking the event loop. Weather tools are sync but wrapped with `retry_on_failure`.

6. **Multi-provider aggregation with degradation** — Weather queries cascade: open-meteo → qweather → wttr. Partial provider failures become notes/warnings in the response rather than failing the entire request. Geocoding cascades similarly: offline China gazetteer → Photon → Nominatim, with Amap available only as an explicit opt-in provider.

7. **Place-finder bridge** — `StargazingPlaceFinder` in `placefinder.py` uses only the namespaced public API from `stargazing-place-finder>=0.9.1`. It avoids re-initializing the SPF singleton when parameters haven't changed (compares `_last_params`), preventing repeated GeoTIFF open and PostGIS pool creation.

8. **Pagination with stable resource_id** — `analysis_area` returns `resource_id` keyed on non-pagination query params (MD5 of sorted kwargs). Cache TTL is 3600s. Cache key excludes `page` and `page_size`, so paginating through results hits the same cache entry.

9. **Retry with exponential backoff** — `retry_on_failure` supports both sync and async functions. Default: 3 attempts, 1s base delay, 30s max, 2x backoff. Used by weather tools for transient network errors.

10. **Docker dual-service via supervisord** — Production container runs both MCP server (:3001) and SPF web UI (:5001) via supervisord. Both services share the same venv and use `uv run` for startup. See `supervisord.conf` for process definitions.

11. **Shared dependency via PyPI** — `stargazing-core` is published to PyPI and consumed by both `mcp-stargazing` and `stargazing-place-finder`. No `[tool.uv.sources]` path overrides in committed config — all dependencies resolve from the registry, ensuring deduplication at build time.

## Testing

- Config in `pyproject.toml`: `pythonpath = ["src"]`, `testpaths = ["tests"]`
- Full pytest suite covering all 17 MCP tools, error paths, edge cases, protocols, docs contracts, and config
- `test_mcp_client.py` — MCP protocol tests (tools/list, tools/call, SSE request-id)
- `test_mcp_tools.py` — every tool's `.fn` wrapper (success + error + edge cases)
- `test_supervisord_config.py` — 15 tests: supervisor config ↔ Dockerfile consistency
- `test_serialization.py` — Every tool's response validates against expected JSON schema
- `test_structured_errors.py` — Business error payload normalization
- `test_tool_metadata.py` — Tool metadata registry vs tools/list alignment
- CI enforces **100% diff-cover** on PRs
- Tests run inside Docker in CI; FastMCP stub available in `server_instance.py` for test environments

## Known Sharp Edges

### Active issues (verified 2026-10-23)

- **Python 3.13+ only** — this is an intentional deployment constraint in `pyproject.toml`.

### Resolved or mitigated

- `AnalysisCache`, object caches, and constellation caches are now lock-protected.
- QWeather URL construction is separated from shared HTTP transport and error translation.
- Weather providers now share one adapter execution contract and registry; adding a provider no longer duplicates fetch → normalize → response wrapping orchestration.
- The legacy SPF `sys.path` and top-level-module compatibility fallback was removed after raising the minimum SPF version to 0.9.1.
- Structured logging is available through `src/logging_config.py`.
- Telescope tools validate coordinates before constructing `EarthLocation`.

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
| `GEOCODER_PROVIDERS` | Comma-separated geocoder order: `gazetteer`, `photon`, `nominatim`, `amap` (default: gazetteer→photon→nominatim for CJK) |
| `AMAP_KEY` | Amap (高德) API key; used only when `amap` is explicitly listed in `GEOCODER_PROVIDERS` |
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
