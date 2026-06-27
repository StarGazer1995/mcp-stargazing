"""Re-exports of weather Pydantic models for backward compatibility.

New code should import directly from src.schemas or src.schemas.weather.
"""

from src.schemas.weather import (
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
