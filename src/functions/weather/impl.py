from src.functions.weather.providers.qweather import get_qweather_auth_from_env
from src.functions.weather.service import (
    get_aggregated_weather_by_name,
    get_aggregated_weather_by_position,
)
from src.response import MCPError, format_error, format_response
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
    try:
        return operation()
    except MCPError as exc:
        return exc.to_response()


def _format_weather_result(result: AggregatedWeatherResponse | dict) -> dict:
    """Serialize weather results into the standard MCP success payload."""
    if isinstance(result, AggregatedWeatherResponse):
        return format_response(result.model_dump())
    return format_response(result)


def _execute_weather_fetch(fetch_weather, error_details: dict) -> dict:
    """Run a weather fetch and translate failures into standard error payloads.

    Individual provider failures are handled at the service layer —
    this wrapper only catches failures that escape the aggregation.
    """

    try:
        return _format_weather_result(fetch_weather())
    except MCPError as exc:
        return exc.to_response()
    except Exception as exc:
        return format_error(
            MCPError.EXTERNAL_API_ERROR,
            f'天气查询失败: {exc}',
            error_details,
        )


def _get_qweather_auth_from_env() -> tuple[str | None, str | None, str | None]:
    """兼容旧测试入口，返回 QWeather 鉴权与 Host 配置。"""

    return get_qweather_auth_from_env()


@mcp.tool()
def get_weather_by_name(place_name: str, provider: str = 'all'):
    """
    通过地点名称获取综合天气（当前 + 小时预报 + 日预报）。

    每个天气 provider 内部自行处理地名→坐标解析（Open-Meteo Geocoding、
    wttr.in 原生地名支持、QWeather POI lookup），不再依赖统一 geocoding 层。
    Weather data is aggregated from multiple providers with graceful
    fallback — open-meteo is always available without an API key.

    Args:
        place_name: 地点名称（例如城市/区县）。
        provider: provider 模式，可选 all/qweather/open-meteo/wttr。

    Returns:
        Dict，包含 keys: "data", "_meta"（成功时）或 "error", "_meta"（失败时）。
    """

    def operation() -> dict:
        cleaned_name = _normalize_place_name(place_name)
        normalized_provider = _normalize_provider(provider)
        return _execute_weather_fetch(
            lambda: get_aggregated_weather_by_name(cleaned_name, provider=normalized_provider),
            {'place_name': cleaned_name},
        )

    return _respond_with_mcp_error(operation)


@mcp.tool()
def get_weather_by_position(lat: float, lon: float, provider: str = 'all'):
    """
    通过经纬度获取综合天气（当前 + 小时预报 + 日预报）。

    Weather data is aggregated from multiple providers with graceful
    fallback — open-meteo is always available without an API key.

    Args:
        lat: 纬度
        lon: 经度
        provider: provider 模式，可选 all/qweather/open-meteo/wttr。

    Returns:
        Dict，包含 keys: "data", "_meta"（成功时）或 "error", "_meta"（失败时）。
    """

    def operation() -> dict:
        _validate_weather_coordinates(lat, lon)
        normalized_provider = _normalize_provider(provider)
        return _execute_weather_fetch(
            lambda: get_aggregated_weather_by_position(lat, lon, provider=normalized_provider),
            {'lat': lat, 'lon': lon},
        )

    return _respond_with_mcp_error(operation)
