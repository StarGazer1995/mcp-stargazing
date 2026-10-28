from src.functions.weather.providers.qweather import get_qweather_auth_from_env
from src.functions.weather.service import (
    get_aggregated_weather_by_name,
    get_aggregated_weather_by_position,
)
from src.logging_config import set_request_id
from src.response import MCPError, format_response
from src.retry import RetryConfig, retry_on_failure
from src.schemas.weather import AggregatedWeatherResponse
from src.server_instance import mcp
from src.utils import validate_coordinates

WEATHER_PROVIDERS = {'all', 'qweather', 'open-meteo', 'wttr'}


def _normalize_provider(provider: str) -> str:
    """Validate and normalize the provider name."""
    normalized = provider.strip().lower()
    if normalized not in WEATHER_PROVIDERS:
        raise MCPError(
            MCPError.CONFIGURATION_ERROR,
            f"Unsupported provider: '{provider}'. Allowed: {sorted(WEATHER_PROVIDERS)}",
            {'provider': provider},
        )
    return normalized


def _normalize_place_name(place_name: str) -> str:
    """Validate and normalize a place name query."""
    cleaned_name = place_name.strip()
    if not cleaned_name:
        raise MCPError(
            MCPError.CONFIGURATION_ERROR,
            'place_name 不能为空。',
            {'place_name': place_name},
        )
    return cleaned_name


def _validate_weather_coordinates(lat: float, lon: float) -> None:
    """Validate latitude and longitude for weather queries."""
    if not validate_coordinates(lat, lon):
        raise MCPError(
            MCPError.INVALID_COORDINATES,
            f'Invalid coordinates: lat={lat}, lon={lon}',
            {'lat': lat, 'lon': lon},
        )


def _respond_with_mcp_error(operation):
    """Convert MCPError exceptions into the standard response payload."""
    set_request_id()
    try:
        return operation()
    except MCPError as exc:
        return exc.to_response()


def _format_weather_result(result: AggregatedWeatherResponse | dict) -> dict:
    """Serialize weather results into the standard MCP success payload."""
    if isinstance(result, AggregatedWeatherResponse):
        return format_response(result.model_dump())
    return format_response(result)


def _execute_weather_capability(fetch_weather, error_details: dict):
    """Run a weather fetch with retries and raise transport-free structured errors."""

    @retry_on_failure(
        RetryConfig(max_attempts=3, base_delay=1.0, max_delay=10.0),
        retryable_errors=(ConnectionError, TimeoutError, OSError),
    )
    def _fetch_weather():
        return fetch_weather()

    try:
        return _fetch_weather()
    except MCPError:
        raise
    except Exception as exc:
        raise MCPError(
            MCPError.EXTERNAL_API_ERROR,
            f'天气查询失败: {exc}',
            error_details,
        ) from exc


def fetch_weather_by_name_capability(
    place_name: str, provider: str = 'all'
) -> AggregatedWeatherResponse | dict:
    """Fetch normalized weather by place name without an MCP response envelope."""
    cleaned_name = _normalize_place_name(place_name)
    normalized_provider = _normalize_provider(provider)
    return _execute_weather_capability(
        lambda: get_aggregated_weather_by_name(cleaned_name, provider=normalized_provider),
        {'place_name': cleaned_name},
    )


def fetch_weather_by_position_capability(
    lat: float, lon: float, provider: str = 'all'
) -> AggregatedWeatherResponse | dict:
    """Fetch normalized weather by coordinates without an MCP response envelope."""
    _validate_weather_coordinates(lat, lon)
    normalized_provider = _normalize_provider(provider)
    return _execute_weather_capability(
        lambda: get_aggregated_weather_by_position(lat, lon, provider=normalized_provider),
        {'lat': lat, 'lon': lon},
    )


def _get_qweather_auth_from_env() -> tuple[str | None, str | None, str | None]:
    """兼容旧测试入口，返回 QWeather 鉴权与 Host 配置。"""

    return get_qweather_auth_from_env()


@mcp.tool()
def get_weather_by_name(place_name: str, provider: str = 'all'):
    """
    通过地点名称获取综合天气（当前 + 小时预报 + 日预报）。

    Use when: you have a place name and need weather facts for that resolved location.
    Do not use when: you already have exact coordinates or need a complete observing decision.
    Requires: an unambiguous place name; use full administrative names for Chinese locations.
        Provider selection can remain at the server's default aggregation policy.
    Follow-up: get_weather_by_position for precise coordinates; plan_stargazing_session
        to combine weather with darkness, targets, and alternative observing sites.

    Geocoding uses offline China gazetteer (CJK) → Photon → Nominatim cascade.
    Weather data is aggregated from multiple providers with graceful
    fallback. Open-Meteo needs no API key; network/provider failures can still occur.
    Interpretation: summary.current is current weather, summary.daily is calendar-day
    aggregation, and summary.hourly contains timestamped forecasts. For a future observing
    night select the actual hourly timestamps across local midnight and inspect providers
    and source for failures/provenance. Missing/null or out-of-horizon hours are unknown,
    not clear weather. Forecasts are predictions, not observations of future conditions;
    do not assume all providers or fields cover the same dates.

    **中文地名提示**：建议使用完整行政区划名称，如 "浙江安吉"、"杭州西湖区"。
    内置离线行政区划数据会正确解析到对应的行政区（如安吉县），而非 POI 商铺。
    需要精确定位时优先使用 ``get_weather_by_position(lat, lon)``。

    Args:
        place_name: 地点名称。中文请使用完整行政区划（如 "浙江省安吉县"），避免仅用2-3字短名。
        provider: provider 模式，可选 all/qweather/open-meteo/wttr。

    Returns:
        Dict，包含 keys: "data", "_meta"（成功时）或 "error", "_meta"（失败时）。
    """

    def operation() -> dict:
        return _format_weather_result(fetch_weather_by_name_capability(place_name, provider))

    return _respond_with_mcp_error(operation)


@mcp.tool()
def get_weather_by_position(lat: float, lon: float, provider: str = 'all'):
    """
    通过经纬度获取综合天气（当前 + 小时预报 + 日预报）。

    Use when: you have precise coordinates and need current and forecast weather facts.
    Do not use when: you only have a place name or need ranked observing sites or night targets.
    Requires: latitude and longitude; provider selection can remain at the default policy.
    Follow-up: get_weather_by_name for place-name input; plan_stargazing_session
        to compare observing places and nights using weather and other evidence.

    Weather data is aggregated from multiple providers with graceful
    fallback. Open-Meteo needs no API key; network/provider failures can still occur.
    Interpretation: summary.current is current weather, summary.daily is calendar-day
    aggregation, and summary.hourly contains timestamped forecasts. For a future observing
    night select the actual hourly timestamps across local midnight and inspect providers
    and source for failures/provenance. Missing/null or out-of-horizon hours are unknown,
    not clear weather. Forecasts are predictions, not observations of future conditions;
    do not assume all providers or fields cover the same dates.

    Args:
        lat: 纬度
        lon: 经度
        provider: provider 模式，可选 all/qweather/open-meteo/wttr。

    Returns:
        Dict，包含 keys: "data", "_meta"（成功时）或 "error", "_meta"（失败时）。
    """

    def operation() -> dict:
        return _format_weather_result(fetch_weather_by_position_capability(lat, lon, provider))

    return _respond_with_mcp_error(operation)
