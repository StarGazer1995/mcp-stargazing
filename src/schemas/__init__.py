"""Shared Pydantic models for the MCP Stargazing server.

These models define the contract between modules — any internal function
should accept and return these models rather than raw dicts.
"""

from src.schemas.base import (
    GeoBounds,
    GeoPoint,
    ProviderType,
    TimeInfo,
)
from src.schemas.celestial import (
    CelestialPosition,
    ConstellationInfo,
    DeepSkyObject,
    MoonInfo,
    NightlyForecast,
    NightWindow,
    RiseSet,
    VisiblePlanet,
)
from src.schemas.error import ErrorCode
from src.schemas.pagination import PaginatedResult
from src.schemas.places import (
    AnalysisAreaResult,
    LightPollutionGrid,
    LightPollutionGridPoint,
    StargazingLocation,
)
from src.schemas.planning import (
    BestStargazingPlan,
    MultiNightPlanningQuery,
    MultiNightPlanningSummary,
    MultiNightStargazingPlan,
    NightlyStargazingPlan,
    ObservationStyle,
    ObservationWindow,
    PlannedLocationCandidate,
    PlanningQuery,
    PlanningSummary,
    PlanningTarget,
    RecommendationDriver,
    WeatherPlanningSummary,
)
from src.schemas.weather import (
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
    'NightWindow',
    'VisiblePlanet',
    'ConstellationInfo',
    'DeepSkyObject',
    'NightlyForecast',
    # Planning
    'PlanningQuery',
    'ObservationStyle',
    'ObservationWindow',
    'WeatherPlanningSummary',
    'PlanningTarget',
    'PlannedLocationCandidate',
    'PlanningSummary',
    'RecommendationDriver',
    'BestStargazingPlan',
    'MultiNightPlanningQuery',
    'MultiNightPlanningSummary',
    'MultiNightStargazingPlan',
    'NightlyStargazingPlan',
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
