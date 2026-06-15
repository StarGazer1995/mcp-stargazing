from pydantic import BaseModel, Field, field_validator

from src.functions.weather.providers.qweather import get_qweather_auth_from_env
from src.functions.weather.service import (
    get_aggregated_weather_by_name,
    get_aggregated_weather_by_position,
)
from src.models import GeoPoint
from src.models.weather import AggregatedWeatherResponse
from src.response import MCPError, format_response
from src.retry import RetryConfig, retry_on_failure
from src.server_instance import mcp


class WeatherQuery(BaseModel):
    """Validated input for weather queries."""

    provider: str = Field(default='all')

    @field_validator('provider')
    @classmethod
    def normalize_provider(cls, v: str) -> str:
        normalized = v.strip().lower()
        allowed = {'all', 'qweather', 'open-meteo', 'wttr'}
        if normalized not in allowed:
            raise ValueError(f"Unsupported provider: '{v}'. Allowed: {sorted(allowed)}")
        return normalized


def _get_qweather_auth_from_env() -> tuple[str | None, str | None, str | None]:
    """兼容旧测试入口，返回 QWeather 鉴权与 Host 配置。"""

    return get_qweather_auth_from_env()


@mcp.tool()
def get_weather_by_name(place_name: str, provider: str = 'all'):
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
            'place_name 不能为空。',
            {'place_name': place_name},
        )
    WeatherQuery(provider=provider)  # validates via Pydantic

    @retry_on_failure(
        RetryConfig(max_attempts=3, base_delay=1.0, max_delay=10.0),
        retryable_errors=(ConnectionError, TimeoutError, OSError),
    )
    def _fetch_weather():
        return get_aggregated_weather_by_name(cleaned_name, provider=provider)

    result = _fetch_weather()
    if isinstance(result, AggregatedWeatherResponse):
        return format_response(result.model_dump())
    return format_response(result)


@mcp.tool()
def get_weather_by_position(lat: float, lon: float, provider: str = 'all'):
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
    GeoPoint(lat=lat, lon=lon)  # validates via Pydantic
    WeatherQuery(provider=provider)  # validates via Pydantic

    @retry_on_failure(
        RetryConfig(max_attempts=3, base_delay=1.0, max_delay=10.0),
        retryable_errors=(ConnectionError, TimeoutError, OSError),
    )
    def _fetch_weather():
        return get_aggregated_weather_by_position(lat, lon, provider=provider)

    result = _fetch_weather()
    if isinstance(result, AggregatedWeatherResponse):
        return format_response(result.model_dump())
    return format_response(result)
