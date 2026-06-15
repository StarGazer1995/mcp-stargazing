"""Shared Pydantic models for the MCP Stargazing server.

These models define the contract between modules — any internal function
should accept and return these models rather than raw dicts.
"""

from src.models.base import (
    GeoBounds,
    GeoPoint,
    ProviderType,
    TimeInfo,
)
from src.models.celestial import (
    CelestialPosition,
    ConstellationInfo,
    DeepSkyObject,
    MoonInfo,
    NightlyForecast,
    RiseSet,
    VisiblePlanet,
)
from src.models.error import ErrorCode
from src.models.pagination import PaginatedResult
from src.models.places import (
    AnalysisAreaResult,
    LightPollutionGrid,
    LightPollutionGridPoint,
    StargazingLocation,
)
from src.models.weather import (
    AggregatedWeatherResponse,
    CurrentWeather,
    DailyForecastItem,
    HourlyForecastItem,
    LocationInfo,
    NormalizedWeatherData,
    ProviderError,
    ProviderErrorDetail,
    ProviderResult,
    ProviderSuccess,
    SourceMeta,
    WeatherSummary,
)

__all__ = [
    'GeoPoint',
    'GeoBounds',
    'TimeInfo',
    'ProviderType',
    'ErrorCode',
    'PaginatedResult',
    # Celestial
    'CelestialPosition',
    'RiseSet',
    'MoonInfo',
    'VisiblePlanet',
    'ConstellationInfo',
    'DeepSkyObject',
    'NightlyForecast',
    # Places
    'LightPollutionGridPoint',
    'LightPollutionGrid',
    'StargazingLocation',
    'AnalysisAreaResult',
    # Weather
    'LocationInfo',
    'CurrentWeather',
    'DailyForecastItem',
    'HourlyForecastItem',
    'NormalizedWeatherData',
    'ProviderSuccess',
    'ProviderError',
    'ProviderErrorDetail',
    'ProviderResult',
    'WeatherSummary',
    'SourceMeta',
    'AggregatedWeatherResponse',
]
