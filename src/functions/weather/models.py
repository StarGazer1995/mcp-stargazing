"""Re-exports of weather Pydantic models for backward compatibility.

New code should import directly from src.models or src.models.weather.
"""

from src.models.weather import (
    AggregatedWeatherResponse,
    CurrentWeather,
    DailyForecastItem,
    HourlyForecastItem,
    LocationInfo,
    NormalizedWeatherData,
    ProviderError,
    ProviderErrorDetail,
    ProviderSuccess,
    SourceMeta,
    WeatherSummary,
)

__all__ = [
    'LocationInfo',
    'CurrentWeather',
    'DailyForecastItem',
    'HourlyForecastItem',
    'ProviderSuccess',
    'ProviderError',
    'ProviderErrorDetail',
    'NormalizedWeatherData',
    'AggregatedWeatherResponse',
    'WeatherSummary',
    'SourceMeta',
]
