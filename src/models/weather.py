"""Pydantic models for weather domain data.

Replaces the dict-based builder functions in src/functions/weather/models.py
with type-safe, validated Pydantic models.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# ── Location ──────────────────────────────────────────────────────────────


class LocationInfo(BaseModel):
    """Normalized location information for weather results."""

    name: str | None = Field(default=None, description='Human-readable place name')
    lat: float = Field(description='Latitude in decimal degrees')
    lon: float = Field(description='Longitude in decimal degrees')
    timezone: str | None = Field(default=None, description='IANA timezone string')


# ── Current Weather ───────────────────────────────────────────────────────


class CurrentWeather(BaseModel):
    """Current weather conditions at a specific point in time."""

    temperature_c: float | None = Field(default=None, description='Current temperature in Celsius')
    feels_like_c: float | None = Field(default=None, description='Apparent temperature in Celsius')
    humidity: float | None = Field(default=None, description='Relative humidity in percent')
    wind_speed_kph: float | None = Field(default=None, description='Wind speed in km/h')
    wind_direction_deg: float | None = Field(default=None, description='Wind direction in degrees')
    pressure_hpa: float | None = Field(default=None, description='Atmospheric pressure in hPa')
    visibility_km: float | None = Field(default=None, description='Visibility in km')
    cloud_cover_percent: float | None = Field(
        default=None, description='Total cloud cover in percent'
    )
    cloud_cover_low_percent: float | None = Field(
        default=None, description='Low-level cloud cover in percent'
    )
    cloud_cover_mid_percent: float | None = Field(
        default=None, description='Mid-level cloud cover in percent'
    )
    cloud_cover_high_percent: float | None = Field(
        default=None, description='High-level cloud cover in percent'
    )
    weather_code: str | None = Field(
        default=None, description='Internal unified weather code (clear, rain, snow, etc.)'
    )
    weather_text: str | None = Field(default=None, description='Human-readable weather description')
    observation_time: str | None = Field(default=None, description='Observation time string')


# ── Forecast Items ────────────────────────────────────────────────────────


class DailyForecastItem(BaseModel):
    """A single day's weather forecast."""

    date: str = Field(description='Date string (YYYY-MM-DD)')
    temp_min_c: float | None = Field(default=None, description='Minimum temperature in Celsius')
    temp_max_c: float | None = Field(default=None, description='Maximum temperature in Celsius')
    precipitation_probability: float | None = Field(
        default=None, description='Precipitation probability (0.0–1.0)'
    )
    cloud_cover_percent: float | None = Field(default=None, description='Cloud cover in percent')
    weather_code_day: str | None = Field(
        default=None, description='Internal unified weather code for daytime'
    )
    weather_text_day: str | None = Field(
        default=None, description='Human-readable daytime weather description'
    )


class HourlyForecastItem(BaseModel):
    """A single hour's weather forecast."""

    time: str = Field(description='Time string (ISO format or YYYY-MM-DDTHH:MM:SS)')
    temperature_c: float | None = Field(default=None, description='Temperature in Celsius')
    humidity: float | None = Field(default=None, description='Relative humidity in percent')
    precipitation_probability: float | None = Field(
        default=None, description='Precipitation probability (0.0–1.0)'
    )
    wind_speed_kph: float | None = Field(default=None, description='Wind speed in km/h')
    wind_direction_deg: float | None = Field(default=None, description='Wind direction in degrees')
    cloud_cover_percent: float | None = Field(
        default=None, description='Total cloud cover in percent'
    )
    cloud_cover_low_percent: float | None = Field(
        default=None, description='Low-level cloud cover in percent'
    )
    cloud_cover_mid_percent: float | None = Field(
        default=None, description='Mid-level cloud cover in percent'
    )
    cloud_cover_high_percent: float | None = Field(
        default=None, description='High-level cloud cover in percent'
    )
    weather_code: str | None = Field(default=None, description='Internal unified weather code')
    weather_text: str | None = Field(default=None, description='Human-readable weather description')


# ── Provider Results ──────────────────────────────────────────────────────


class NormalizedWeatherData(BaseModel):
    """The normalized weather data returned by a single provider."""

    location: LocationInfo = Field(description='Resolved location information')
    current: CurrentWeather = Field(description='Current weather conditions')
    daily: list[DailyForecastItem] = Field(default_factory=list, description='Daily forecast list')
    hourly: list[HourlyForecastItem] = Field(
        default_factory=list, description='Hourly forecast list'
    )


class ProviderSuccess(BaseModel):
    """A successful provider query result."""

    status: str = Field(default='success', description='Status indicator')
    provider: str = Field(description='Provider name')
    data: NormalizedWeatherData = Field(description='Normalized weather data from this provider')


class ProviderErrorDetail(BaseModel):
    """Details of a provider error."""

    code: str = Field(description='Error code')
    message: str = Field(description='Error message')
    details: dict[str, Any] | None = Field(default=None, description='Additional error context')


class ProviderError(BaseModel):
    """A failed provider query result."""

    status: str = Field(default='error', description='Status indicator')
    provider: str = Field(description='Provider name')
    error: ProviderErrorDetail = Field(description='Error details')


ProviderResult = ProviderSuccess | ProviderError
"""Union type for provider query results (success or error)."""


# ── Aggregated Response ───────────────────────────────────────────────────


class WeatherSummary(BaseModel):
    """Merged weather summary from multiple providers."""

    current: dict[str, Any] = Field(
        default_factory=dict, description='Merged current weather (field-level fallback)'
    )
    daily: list[dict[str, Any]] = Field(
        default_factory=list, description='Daily forecast from primary provider'
    )
    hourly: list[dict[str, Any]] = Field(
        default_factory=list, description='Hourly forecast from primary provider'
    )


class SourceMeta(BaseModel):
    """Metadata about which providers were used for the aggregated result."""

    query_mode: str = Field(description='The original provider filter requested')
    successful_providers: list[str] = Field(
        default_factory=list, description='Providers that returned data'
    )
    failed_providers: list[str] = Field(default_factory=list, description='Providers that failed')
    summary_provider_policy: str = Field(
        default='open-meteo-first', description='Policy used to select summary provider'
    )


class AggregatedWeatherResponse(BaseModel):
    """The top-level aggregated weather response."""

    location: LocationInfo = Field(description='Resolved location')
    summary: WeatherSummary = Field(description='Merged weather summary')
    providers: dict[str, ProviderResult] = Field(
        description='Per-provider raw results (success or error)'
    )
    source: SourceMeta = Field(description='Provider source metadata')
