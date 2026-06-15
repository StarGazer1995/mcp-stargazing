"""Shared Pydantic models for the MCP Stargazing server.

These models define the contract between modules — any internal function
should accept and return these models rather than raw dicts.
"""

from src.models.base import (
    GeoPoint,
    GeoBounds,
    TimeInfo,
    ProviderType,
)
from src.models.celestial import (
    CelestialPosition,
    RiseSet,
    MoonInfo,
    VisiblePlanet,
    ConstellationInfo,
    DeepSkyObject,
    NightlyForecast,
)
from src.models.error import ErrorCode
from src.models.pagination import PaginatedResult
from src.models.places import (
    LightPollutionGridPoint,
    LightPollutionGrid,
    StargazingLocation,
    AnalysisAreaResult,
)
from src.models.weather import (
    LocationInfo,
    CurrentWeather,
    DailyForecastItem,
    HourlyForecastItem,
    NormalizedWeatherData,
    ProviderSuccess,
    ProviderError,
    ProviderErrorDetail,
    ProviderResult,
    WeatherSummary,
    SourceMeta,
    AggregatedWeatherResponse,
)

__all__ = [
    "GeoPoint",
    "GeoBounds",
    "TimeInfo",
    "ProviderType",
    "ErrorCode",
    "PaginatedResult",
    # Celestial
    "CelestialPosition",
    "RiseSet",
    "MoonInfo",
    "VisiblePlanet",
    "ConstellationInfo",
    "DeepSkyObject",
    "NightlyForecast",
    # Places
    "LightPollutionGridPoint",
    "LightPollutionGrid",
    "StargazingLocation",
    "AnalysisAreaResult",
    # Weather
    "LocationInfo",
    "CurrentWeather",
    "DailyForecastItem",
    "HourlyForecastItem",
    "NormalizedWeatherData",
    "ProviderSuccess",
    "ProviderError",
    "ProviderErrorDetail",
    "ProviderResult",
    "WeatherSummary",
    "SourceMeta",
    "AggregatedWeatherResponse",
]
