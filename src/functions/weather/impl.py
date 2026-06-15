from src.server_instance import mcp
from src.functions.weather.providers.qweather import get_qweather_auth_from_env
from src.functions.weather.service import (
    get_aggregated_weather_by_name,
    get_aggregated_weather_by_position,
)
from src.response import format_response, MCPError
from src.retry import retry_on_failure, RetryConfig


def _get_qweather_auth_from_env() -> tuple[str | None, str | None, str | None]:
    """兼容旧测试入口，返回 QWeather 鉴权与 Host 配置。"""

    return get_qweather_auth_from_env()


@mcp.tool()
def get_weather_by_name(place_name: str, provider: str = "all"):
    """
    通过地点名称获取综合天气（当前 + 小时预报 + 日预报）。

    Args:
        place_name: 地点名称（例如城市/区县）。
        provider: provider 模式，可选 all/qweather/open-meteo/wttr。

    Returns:
        Dict，包含 keys: "data", "_meta"。

    Raises:
        MCPError: For validation failures, API errors, or network issues.
    """
    cleaned_name = place_name.strip()
    if not cleaned_name:
        raise MCPError(
            MCPError.CONFIGURATION_ERROR,
            "place_name 不能为空。",
            {"place_name": place_name},
        )
    normalized_provider = _validate_provider(provider)

    @retry_on_failure(
        RetryConfig(max_attempts=3, base_delay=1.0, max_delay=10.0),
        retryable_errors=(ConnectionError, TimeoutError, OSError)
    )
    def _fetch_weather():
        return get_aggregated_weather_by_name(cleaned_name, provider=normalized_provider)

    result = _fetch_weather()
    return format_response(result)


@mcp.tool()
def get_weather_by_position(lat: float, lon: float, provider: str = "all"):
    """
    通过经纬度获取综合天气（当前 + 小时预报 + 日预报）。

    Args:
        lat: 纬度
        lon: 经度
        provider: provider 模式，可选 all/qweather/open-meteo/wttr。

    Returns:
        Dict，包含 keys: "data", "_meta"。

    Raises:
        MCPError: For validation failures, API errors, or network issues.
    """
    _validate_coordinates(lat, lon)
    normalized_provider = _validate_provider(provider)

    @retry_on_failure(
        RetryConfig(max_attempts=3, base_delay=1.0, max_delay=10.0),
        retryable_errors=(ConnectionError, TimeoutError, OSError)
    )
    def _fetch_weather():
        return get_aggregated_weather_by_position(lat, lon, provider=normalized_provider)

    result = _fetch_weather()
    return format_response(result)


def _validate_provider(provider: str) -> str:
    """校验 provider 参数并返回规范化值。"""

    normalized = provider.strip().lower()
    allowed = {"all", "qweather", "open-meteo", "wttr"}
    if normalized not in allowed:
        raise MCPError(
            MCPError.CONFIGURATION_ERROR,
            f"不支持的天气 provider: {provider}",
            {"provider": provider, "allowed": sorted(allowed)},
        )
    return normalized


def _validate_coordinates(lat: float, lon: float) -> None:
    """校验经纬度是否合法。"""

    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        raise MCPError(
            MCPError.INVALID_COORDINATES,
            f"Invalid coordinates: lat={lat}, lon={lon}",
            {"lat": lat, "lon": lon},
        )
