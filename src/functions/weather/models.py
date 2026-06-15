"""Re-exports of weather Pydantic models for backward compatibility.

New code should import directly from src.models or src.models.weather.
"""

from src.models.weather import (
    LocationInfo,
    CurrentWeather,
    DailyForecastItem,
    HourlyForecastItem,
    ProviderSuccess,
    ProviderError,
    ProviderErrorDetail,
    NormalizedWeatherData,
    AggregatedWeatherResponse,
    WeatherSummary,
    SourceMeta,
)

__all__ = [
    "LocationInfo",
    "CurrentWeather",
    "DailyForecastItem",
    "HourlyForecastItem",
    "ProviderSuccess",
    "ProviderError",
    "ProviderErrorDetail",
    "NormalizedWeatherData",
    "AggregatedWeatherResponse",
    "WeatherSummary",
    "SourceMeta",
]
