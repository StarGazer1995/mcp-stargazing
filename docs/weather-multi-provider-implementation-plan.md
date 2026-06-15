# Weather Multi-Provider Implementation Plan

## 1. Goal

This document describes the implementation plan for refactoring the weather module into a multi-provider aggregation architecture.

The target providers are:

- `open-meteo`
- `QWeather`
- `wttr.in`

The target behavior is:

- Keep the existing MCP tool entrypoints stable.
- Query all configured weather providers for a request.
- Normalize provider responses into one internal schema.
- Return one aggregated weather payload plus each provider's status and data.
- Expose cloud-cover information as part of the public weather interface.
- Expose hour-level forecast data as part of the public weather interface.
- Keep the implementation simple, explicit, and easy to maintain.

## 2. Design Principles

- Keep `src/functions/weather/impl.py` as a thin MCP entry layer.
- Move provider-specific logic into dedicated files under `src/functions/weather/providers/`.
- Use one shared service layer to orchestrate provider lookup and aggregation.
- Use one shared schema builder layer to keep response shape stable.
- Prefer simple functions over complex inheritance or abstract frameworks.
- Add function-level comments for newly created functions.
- Keep the first version focused on correctness and clarity rather than advanced optimization.

## 3. Target Query Behavior

The weather tools should support the following provider modes:

- `all`: query all weather providers
- `qweather`: query only QWeather
- `open-meteo`: query only Open-Meteo
- `wttr`: query only wttr.in

The default mode should be `all`.

For `provider="all"`:

- Query all enabled providers.
- Keep the result even if one or more providers fail.
- Return success if at least one provider succeeds.
- Return an error only if all providers fail.

## 4. Response Shape

The final MCP `data` payload should follow this shape:

```json
{
  "location": {
    "name": "Beijing",
    "lat": 39.9042,
    "lon": 116.4074,
    "timezone": "Asia/Shanghai"
  },
  "summary": {
    "current": {
      "temperature_c": 26.1,
      "feels_like_c": 27.3,
      "humidity": 58,
      "wind_speed_kph": 12.3,
      "wind_direction_deg": 230,
      "pressure_hpa": 1008.4,
      "visibility_km": 10.0,
      "cloud_cover_percent": 72,
      "cloud_cover_low_percent": 18,
      "cloud_cover_mid_percent": 34,
      "cloud_cover_high_percent": 52,
      "weather_code": "partly_cloudy",
      "weather_text": "Partly cloudy",
      "observation_time": "2026-06-15T10:00:00+08:00"
    },
    "daily": [
      {
        "date": "2026-06-15",
        "temp_min_c": 21.0,
        "temp_max_c": 29.0,
        "precipitation_probability": 0.35,
        "cloud_cover_percent": 68,
        "weather_code_day": "cloudy",
        "weather_text_day": "Cloudy"
      }
    ],
    "hourly": [
      {
        "time": "2026-06-15T11:00:00+08:00",
        "temperature_c": 26.8,
        "humidity": 56,
        "precipitation_probability": 0.20,
        "wind_speed_kph": 14.2,
        "wind_direction_deg": 225,
        "cloud_cover_percent": 70,
        "cloud_cover_low_percent": 16,
        "cloud_cover_mid_percent": 31,
        "cloud_cover_high_percent": 50,
        "weather_code": "partly_cloudy",
        "weather_text": "Partly cloudy"
      }
    ]
  },
  "providers": {
    "open-meteo": {
      "status": "success",
      "provider": "open-meteo",
      "data": {}
    },
    "qweather": {
      "status": "success",
      "provider": "qweather",
      "data": {}
    },
    "wttr": {
      "status": "error",
      "provider": "wttr",
      "error": {
        "code": "API_TIMEOUT",
        "message": "wttr.in request timed out"
      }
    }
  },
  "source": {
    "query_mode": "all",
    "successful_providers": [
      "open-meteo",
      "qweather"
    ],
    "failed_providers": [
      "wttr"
    ],
    "summary_provider_policy": "open-meteo-first"
  }
}
```

Cloud-cover fields are required for external consumers.

Field notes:

- `cloud_cover_percent`: total cloud cover percentage, recommended range \( 0 \le x \le 100 \)
- `cloud_cover_low_percent`: low-cloud percentage when the provider exposes low-level cloud layers
- `cloud_cover_mid_percent`: mid-cloud percentage when available
- `cloud_cover_high_percent`: high-cloud percentage when available
- `hourly`: hour-level forecast array using ISO timestamps in the `time` field

Hourly forecast fields should be normalized to the same units as `summary.current`.

If a provider does not expose layered cloud information, the layer-specific fields should be returned as `null`.

## 5. Proposed File Layout

```text
src/functions/weather/
├── __init__.py
├── impl.py
├── service.py
├── models.py
├── geocoding.py
└── providers/
    ├── __init__.py
    ├── qweather.py
    ├── open_meteo.py
    └── wttr.py
```

## 6. File Responsibilities

### `src/functions/weather/impl.py`

Responsibilities:

- Expose MCP tools with `@mcp.tool()`.
- Validate user input.
- Apply retry behavior around the service layer.
- Call the service functions.
- Wrap successful results with `format_response(...)`.
- Surface structured failures with `MCPError`.

This file should not:

- Call provider-specific APIs directly.
- Build summary logic.
- Translate provider-specific fields.

### `src/functions/weather/service.py`

Responsibilities:

- Resolve which providers should be queried.
- Orchestrate provider lookup by coordinates.
- Build the final aggregated response.
- Decide provider success and failure handling.
- Build `summary`, `providers`, and `source`.
- Build `summary.hourly` as part of the external result.

This is the main orchestration layer.

### `src/functions/weather/models.py`

Responsibilities:

- Build stable payload shapes for weather data.
- Provide helper constructors for `location`, `current`, `daily`, `hourly`, `provider`, and aggregated payloads.
- Keep field naming consistent across all providers.
- Ensure cloud-cover fields are normalized consistently across providers.

### `src/functions/weather/geocoding.py`

Responsibilities:

- Resolve a place name into normalized location data.
- Return `name`, `lat`, `lon`, and `timezone` when available.
- Keep geocoding logic separate from provider weather logic.

### `src/functions/weather/providers/qweather.py`

Responsibilities:

- Query QWeather weather endpoints.
- Normalize QWeather fields into the shared weather schema.
- Translate QWeather-specific errors into `MCPError`.
- Map QWeather cloud data into the shared cloud-cover fields when available.
- Map QWeather hourly forecast data when the upstream API exposes compatible hourly fields.

### `src/functions/weather/providers/open_meteo.py`

Responsibilities:

- Query Open-Meteo by coordinates.
- Normalize Open-Meteo fields into the shared weather schema.
- Act as the preferred provider for `daily` forecast data in summary generation.
- Treat Open-Meteo as the preferred source for cloud-cover data when cloud fields are available.
- Act as the preferred provider for `hourly` forecast data in summary generation.

### `src/functions/weather/providers/wttr.py`

Responsibilities:

- Query wttr.in by coordinates.
- Normalize wttr.in fields into the shared weather schema.
- Provide a lightweight supplemental provider in aggregated responses.
- Surface cloud-cover data when wttr.in exposes it, otherwise keep cloud fields as `None`.
- Surface hourly forecast data when wttr.in exposes it, otherwise keep hourly-only fields as `None`.

## 7. Function Signatures And Responsibilities

### 7.1 `impl.py`

```python
@mcp.tool()
def get_weather_by_name(
    place_name: str,
    provider: str = "all",
) -> dict:
    """通过地点名称获取综合天气信息。"""
```

Responsibilities:

- Validate that `place_name` is not empty.
- Validate and normalize `provider`.
- Call `service.get_aggregated_weather_by_name(...)`.
- Return `format_response(...)`.

```python
@mcp.tool()
def get_weather_by_position(
    lat: float,
    lon: float,
    provider: str = "all",
) -> dict:
    """通过经纬度获取综合天气信息。"""
```

Responsibilities:

- Validate coordinate bounds.
- Validate and normalize `provider`.
- Call `service.get_aggregated_weather_by_position(...)`.
- Return `format_response(...)`.

```python
def _validate_provider(provider: str) -> str:
    """校验 provider 参数并返回规范化值。"""
```

Responsibilities:

- Normalize spaces and case.
- Allow only `all`, `qweather`, `open-meteo`, `wttr`.
- Raise `MCPError` on invalid input.

```python
def _validate_coordinates(lat: float, lon: float) -> None:
    """校验经纬度是否合法。"""
```

Responsibilities:

- Validate \( -90 \le lat \le 90 \).
- Validate \( -180 \le lon \le 180 \).

### 7.2 `service.py`

```python
def get_aggregated_weather_by_name(
    place_name: str,
    provider: str = "all",
) -> dict:
    """根据地点名称查询并聚合多个天气提供商的结果。"""
```

Responsibilities:

- Call `geocoding.resolve_place_name(...)`.
- Reuse the coordinate-based aggregation path.
- Preserve resolved location metadata in the final payload.

```python
def get_aggregated_weather_by_position(
    lat: float,
    lon: float,
    provider: str = "all",
    location_name: str | None = None,
    timezone: str | None = None,
) -> dict:
    """根据经纬度查询并聚合多个天气提供商的结果。"""
```

Responsibilities:

- Determine the active provider list.
- Query each selected provider.
- Build the final payload:
  - `location`
  - `summary`
  - `providers`
  - `source`
- Raise an error only if all providers fail.

```python
def get_enabled_providers(provider: str) -> list[str]:
    """根据 provider 参数返回需要查询的 provider 列表。"""
```

Responsibilities:

- Return all providers for `all`.
- Return a one-item list for a single provider mode.
- Keep the canonical provider order stable.

Suggested provider order:

```python
["open-meteo", "qweather", "wttr"]
```

```python
def query_providers_by_position(
    lat: float,
    lon: float,
    provider_names: list[str],
    location_name: str | None = None,
    timezone: str | None = None,
) -> dict:
    """按 provider 列表查询天气，并返回各 provider 的结果状态。"""
```

Responsibilities:

- Query each provider in order.
- Collect `success` or `error` payloads.
- Do not stop after one provider fails.

```python
def _query_single_provider(
    provider_name: str,
    lat: float,
    lon: float,
    location_name: str | None = None,
    timezone: str | None = None,
) -> dict:
    """查询单个 provider 并返回标准化后的 provider 结果。"""
```

Responsibilities:

- Route to `providers.qweather`, `providers.open_meteo`, or `providers.wttr`.
- Return the standardized provider payload.

```python
def _build_summary(provider_results: dict) -> dict:
    """根据多个 provider 的标准化结果生成综合天气摘要。"""
```

Responsibilities:

- Read successful provider results only.
- Build `summary.current`.
- Build `summary.daily`.
- Build `summary.hourly`.
- Keep the logic explicit and easy to inspect.

```python
def _build_summary_current(successful_provider_data: list[dict]) -> dict:
    """从多个成功 provider 中生成统一的当前天气摘要。"""
```

Responsibilities:

- Select one primary provider for summary fields.
- Fill missing fields from other successful providers when possible.
- Keep field selection rules deterministic.

```python
def _build_summary_daily(successful_provider_data: list[dict]) -> list[dict]:
    """从多个成功 provider 中生成统一的日级天气预报摘要。"""
```

Responsibilities:

- Prefer Open-Meteo daily forecast when available.
- Fall back to QWeather daily forecast if needed.
- Fall back to wttr daily forecast if needed.

```python
def _build_summary_hourly(
    successful_provider_data: list[dict],
) -> list[dict]:
    """从多个成功 provider 中生成统一的小时级天气预报摘要。"""
```

Responsibilities:

- Prefer Open-Meteo hourly forecast when available.
- Fall back to QWeather hourly forecast if needed.
- Fall back to wttr hourly forecast if needed.
- Preserve cloud-cover fields in each hourly forecast item whenever possible.

```python
def _select_primary_provider_for_summary(
    successful_provider_data: list[dict],
) -> str | None:
    """选择用于生成摘要的主 provider。"""
```

Responsibilities:

- Use a stable priority rule.
- Suggested priority:
  - `open-meteo`
  - `qweather`
  - `wttr`

```python
def _build_source_meta(
    requested_provider: str,
    provider_results: dict,
) -> dict:
    """根据 provider 查询结果构造来源元信息。"""
```

Responsibilities:

- Collect successful provider names.
- Collect failed provider names.
- Declare the summary selection policy.

```python
def _ensure_any_provider_success(provider_results: dict) -> None:
    """确保至少有一个 provider 查询成功，否则抛出错误。"""
```

Responsibilities:

- Check whether any provider returned `status="success"`.
- Raise an aggregated `MCPError` if all failed.

### 7.3 `models.py`

```python
def build_location_payload(
    name: str | None,
    lat: float,
    lon: float,
    timezone: str | None,
) -> dict:
    """构造统一的位置数据结构。"""
```

Responsibilities:

- Return the standard `location` object.

```python
def build_current_weather_payload(
    temperature_c: float | None = None,
    feels_like_c: float | None = None,
    humidity: float | None = None,
    wind_speed_kph: float | None = None,
    wind_direction_deg: float | None = None,
    pressure_hpa: float | None = None,
    visibility_km: float | None = None,
    cloud_cover_percent: float | None = None,
    cloud_cover_low_percent: float | None = None,
    cloud_cover_mid_percent: float | None = None,
    cloud_cover_high_percent: float | None = None,
    weather_code: str | None = None,
    weather_text: str | None = None,
    observation_time: str | None = None,
) -> dict:
    """构造统一的当前天气数据结构。"""
```

Responsibilities:

- Build the shared `summary.current` shape.

```python
def build_daily_forecast_item(
    date: str,
    temp_min_c: float | None = None,
    temp_max_c: float | None = None,
    precipitation_probability: float | None = None,
    cloud_cover_percent: float | None = None,
    weather_code_day: str | None = None,
    weather_text_day: str | None = None,
) -> dict:
    """构造统一的单日预报数据结构。"""
```

Responsibilities:

- Build one normalized daily forecast item.
- Keep daily cloud-cover output stable for external consumers.

```python
def build_hourly_forecast_item(
    time: str,
    temperature_c: float | None = None,
    humidity: float | None = None,
    precipitation_probability: float | None = None,
    wind_speed_kph: float | None = None,
    wind_direction_deg: float | None = None,
    cloud_cover_percent: float | None = None,
    cloud_cover_low_percent: float | None = None,
    cloud_cover_mid_percent: float | None = None,
    cloud_cover_high_percent: float | None = None,
    weather_code: str | None = None,
    weather_text: str | None = None,
) -> dict:
    """构造统一的单小时预报数据结构。"""
```

Responsibilities:

- Build one normalized hourly forecast item.
- Keep hourly cloud-cover output stable for external consumers.

```python
def build_provider_success_payload(
    provider_name: str,
    data: dict,
) -> dict:
    """构造 provider 成功状态结果。"""
```

Responsibilities:

- Return the standard success wrapper for one provider.

```python
def build_provider_error_payload(
    provider_name: str,
    code: str,
    message: str,
    details: dict | None = None,
) -> dict:
    """构造 provider 失败状态结果。"""
```

Responsibilities:

- Return the standard error wrapper for one provider.

```python
def build_aggregated_weather_payload(
    location: dict,
    summary: dict,
    providers: dict,
    source: dict,
) -> dict:
    """构造最终综合天气响应数据结构。"""
```

Responsibilities:

- Assemble the final normalized result under `data`.

### 7.4 `geocoding.py`

```python
def resolve_place_name(place_name: str) -> dict:
    """将地点名称解析为标准位置对象。"""
```

Responsibilities:

- Resolve place names to coordinates.
- Return normalized location data:
  - `name`
  - `lat`
  - `lon`
  - `timezone`

```python
def _resolve_with_qweather(place_name: str) -> dict:
    """使用 QWeather 地理接口解析地点名称。"""
```

Responsibilities:

- Reuse the existing QWeather geocoding capability for the first version.
- Return the best candidate from QWeather location search.

```python
def normalize_geocoding_result(
    name: str,
    lat: float,
    lon: float,
    timezone: str | None = None,
) -> dict:
    """将地理编码结果标准化为统一位置结构。"""
```

Responsibilities:

- Convert raw geocoding output into the shared location format.

### 7.5 `providers/qweather.py`

```python
def get_weather_by_position(
    lat: float,
    lon: float,
    location_name: str | None = None,
    timezone: str | None = None,
) -> dict:
    """查询 QWeather 并返回标准化后的 provider 结果。"""
```

Responsibilities:

- Fetch QWeather current weather and daily forecast.
- Normalize the raw result.
- Return one provider success payload.

```python
def fetch_qweather_raw_weather(lat: float, lon: float) -> dict:
    """查询 QWeather 原始天气数据。"""
```

Responsibilities:

- Fetch current weather and forecast from QWeather.
- Return raw combined provider data.

```python
def normalize_qweather_weather(
    raw_data: dict,
    lat: float,
    lon: float,
    location_name: str | None = None,
    timezone: str | None = None,
) -> dict:
    """将 QWeather 原始响应映射为统一天气结构。"""
```

Responsibilities:

- Convert QWeather field names into shared schema fields.
- Convert provider-specific condition code to internal code.
- Map cloud-related fields into:
  - `cloud_cover_percent`
  - `cloud_cover_low_percent`
  - `cloud_cover_mid_percent`
  - `cloud_cover_high_percent`
- Map any available hourly forecast entries into the shared `hourly` structure.

```python
def map_qweather_condition_code(code: str | None) -> str | None:
    """将 QWeather 天气代码映射为内部统一 weather_code。"""
```

Responsibilities:

- Map QWeather condition code to the internal weather code set.

### 7.6 `providers/open_meteo.py`

```python
def get_weather_by_position(
    lat: float,
    lon: float,
    location_name: str | None = None,
    timezone: str | None = None,
) -> dict:
    """查询 Open-Meteo 并返回标准化后的 provider 结果。"""
```

Responsibilities:

- Fetch Open-Meteo weather data.
- Normalize current and daily weather into the shared schema.
- Return one provider success payload.

```python
def build_open_meteo_url(
    lat: float,
    lon: float,
    timezone: str | None = None,
) -> str:
    """构造 Open-Meteo 请求 URL。"""
```

Responsibilities:

- Build the full request URL with all required weather fields.

```python
def fetch_open_meteo_raw_weather(
    lat: float,
    lon: float,
    timezone: str | None = None,
) -> dict:
    """查询 Open-Meteo 原始天气数据。"""
```

Responsibilities:

- Perform the HTTP request.
- Translate request failures into `MCPError`.

```python
def normalize_open_meteo_weather(
    raw_data: dict,
    lat: float,
    lon: float,
    location_name: str | None = None,
    timezone: str | None = None,
) -> dict:
    """将 Open-Meteo 原始响应映射为统一天气结构。"""
```

Responsibilities:

- Extract current weather.
- Extract daily forecast.
- Extract hourly forecast.
- Preserve timezone when available.
- Map Open-Meteo cloud fields into the shared cloud-cover fields.

```python
def map_open_meteo_weather_code(code: int | None) -> str | None:
    """将 Open-Meteo 天气代码映射为内部统一 weather_code。"""
```

Responsibilities:

- Convert Open-Meteo weather codes into the internal weather code set.

### 7.7 `providers/wttr.py`

```python
def get_weather_by_position(
    lat: float,
    lon: float,
    location_name: str | None = None,
    timezone: str | None = None,
) -> dict:
    """查询 wttr.in 并返回标准化后的 provider 结果。"""
```

Responsibilities:

- Fetch wttr.in weather data.
- Normalize the result into the shared schema.
- Return one provider success payload.

```python
def build_wttr_query(lat: float, lon: float) -> str:
    """构造 wttr.in 查询字符串。"""
```

Responsibilities:

- Build a stable coordinate query format for wttr.in.

```python
def fetch_wttr_raw_weather(lat: float, lon: float) -> dict:
    """查询 wttr.in 原始天气数据。"""
```

Responsibilities:

- Perform the wttr.in request.
- Translate request or response failures into `MCPError`.

```python
def normalize_wttr_weather(
    raw_data: dict,
    lat: float,
    lon: float,
    location_name: str | None = None,
    timezone: str | None = None,
) -> dict:
    """将 wttr.in 原始响应映射为统一天气结构。"""
```

Responsibilities:

- Extract current weather fields.
- Extract daily forecast fields when available.
- Extract hourly forecast fields when available.
- Leave missing fields as `None`.
- Populate cloud-cover fields when the upstream response includes cloud information.

```python
def map_wttr_condition_text(text: str | None) -> str | None:
    """将 wttr.in 的天气文本映射为内部统一 weather_code。"""
```

Responsibilities:

- Convert wttr.in condition text into internal weather code values.

## 8. Summary Generation Rules

The first version should keep summary logic simple and deterministic.

### `summary.current`

Suggested rules:

- Select one primary provider using this priority:
  - `open-meteo`
  - `qweather`
  - `wttr`
- Take current-weather fields from the primary provider.
- If a field is missing, fill it from other successful providers in priority order.
- Prefer cloud-cover fields from `open-meteo` when available, because cloud amount is a key external requirement.

### `summary.daily`

Suggested rules:

- Prefer `open-meteo` daily forecast.
- Fall back to `qweather` daily forecast if Open-Meteo is unavailable.
- Fall back to `wttr` daily forecast if both others are unavailable.
- Preserve `cloud_cover_percent` in each daily item whenever at least one provider supplies it.

### `summary.hourly`

Suggested rules:

- Prefer `open-meteo` hourly forecast.
- Fall back to `qweather` hourly forecast if Open-Meteo is unavailable.
- Fall back to `wttr` hourly forecast if both others are unavailable.
- Preserve cloud-cover fields in each hourly item whenever at least one provider supplies them.
- Use ISO timestamps for each hourly item in the `time` field.

### Future Enhancement

If needed later, selected numeric fields may use median-based aggregation. For example, if temperatures from three providers are \( T_1 \), \( T_2 \), and \( T_3 \), the summary temperature may be defined as:

\[
T_{\text{summary}} = \mathrm{median}(T_1, T_2, T_3)
\]

This should not be part of the first implementation.

## 9. Error Handling Rules

- Keep using `src.response.MCPError`.
- Translate provider request failures into structured errors.
- Do not leak raw provider exceptions to MCP tools.
- Treat partial provider failure as a successful aggregated response.
- Raise a top-level error only when all selected providers fail.

Recommended mapping:

- timeout -> `API_TIMEOUT`
- authentication failure -> `API_AUTH_FAILURE`
- rate limit -> `API_RATE_LIMIT`
- invalid provider response -> `EXTERNAL_API_ERROR`
- connectivity issue -> `NETWORK_ERROR`
- invalid tool configuration -> `CONFIGURATION_ERROR`

## 10. Implementation Phases

### Phase 1: Create The Structure

- Add `service.py`
- Add `models.py`
- Add `geocoding.py`
- Add `providers/` package and provider files

Output:

- Weather module file layout is ready for provider-based implementation.

### Phase 2: Migrate QWeather

- Move QWeather-specific weather logic into `providers/qweather.py`
- Reuse existing QWeather request and auth helpers where possible

Output:

- QWeather works through the new provider interface.

### Phase 3: Add Open-Meteo

- Implement Open-Meteo request URL builder
- Fetch current, daily, and hourly weather
- Normalize the response

Output:

- Open-Meteo works as a provider and can serve as summary primary source.

### Phase 4: Add wttr.in

- Implement wttr.in fetch and normalization
- Support current weather, daily forecast, and hourly forecast where possible

Output:

- wttr.in works as a supplemental provider.

### Phase 5: Implement Geocoding

- Implement name-to-coordinate resolution in `geocoding.py`
- Reuse QWeather geocoding for the first version

Output:

- `get_weather_by_name(...)` uses a shared location resolution path.

### Phase 6: Implement Aggregation

- Build `query_providers_by_position(...)`
- Build summary logic
- Build provider status collection
- Build final payload assembly

Output:

- Weather service returns a unified aggregated result.

### Phase 7: Update MCP Entry Layer

- Refactor `impl.py` to call the service layer only
- Add `provider: str = "all"`

Output:

- MCP tools expose the new behavior while keeping stable entrypoints.

### Phase 8: Tests

- Add provider normalization tests
- Add aggregation tests
- Update MCP weather tool tests

Output:

- New behavior is covered by tests.

### Phase 9: Documentation

- Update `README.md`
- Update `AGENTS.md` if tool behavior changes materially

Output:

- The new weather tool behavior is documented for contributors and agent users.

## 11. Test Plan

Suggested test files:

- `tests/test_weather.py`
- `tests/test_weather_providers.py`
- `tests/test_weather_normalization.py`

Suggested test scenarios:

- all providers succeed
- one provider fails and others succeed
- only one provider succeeds
- all providers fail
- geocoding succeeds
- geocoding fails
- explicit single-provider query works
- normalized payload shape remains stable

Recommended command:

```bash
pytest tests/ -v
```

## 12. First-Version Scope Control

The first implementation should include:

- provider mode selection
- shared response schema
- QWeather provider
- Open-Meteo provider
- wttr.in provider
- shared geocoding
- aggregated result payload
- cloud-cover fields in `summary.current` and `summary.daily`
- hourly forecast fields in `summary.hourly`
- provider success and error visibility
- tests for aggregation and normalization

The first implementation should not include:

- advanced async concurrency
- weighted provider scoring
- historical weather support
- caching optimization
- sophisticated multi-provider statistical fusion

## 13. Recommended Build Order

Recommended coding order:

1. `models.py`
2. `service.py` skeleton
3. `providers/qweather.py`
4. `providers/open_meteo.py`
5. `providers/wttr.py`
6. `geocoding.py`
7. `impl.py`
8. tests
9. documentation updates

## 14. Completion Criteria

The implementation is complete when:

- `get_weather_by_name(...)` works with `provider="all"`
- `get_weather_by_position(...)` works with `provider="all"`
- at least one provider success returns a valid aggregated payload
- all provider failures return a structured top-level error
- `summary`, `providers`, and `source` are present in the final result
- `summary.hourly` exposes hour-level forecast data
- provider results are normalized to a stable schema
- tests pass from the project root

## 15. Next Step

The next practical step is to convert this plan into code skeleton files, then implement providers one by one in the recommended build order.
