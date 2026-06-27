"""Pydantic models for composite stargazing planning results."""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.models.places import StargazingLocation


class PlanningQuery(BaseModel):
    """Normalized query parameters for a composite planning request."""

    south: float = Field(description='Southern latitude bound')
    west: float = Field(description='Western longitude bound')
    north: float = Field(description='Northern latitude bound')
    east: float = Field(description='Eastern longitude bound')
    time: str = Field(description='Requested observation time string')
    time_zone: str = Field(description='Requested IANA timezone string')
    candidate_limit: int = Field(ge=1, description='Maximum number of candidate places to evaluate')
    target_limit: int = Field(ge=1, description='Maximum number of recommended targets per place')
    weather_provider: str = Field(description='Weather provider mode used for weather summaries')
    max_locations: int = Field(
        ge=1, description='Maximum number of area-analysis candidates searched'
    )
    min_height_diff: float = Field(description='Minimum elevation difference used for place search')
    road_radius_km: float = Field(description='Road search radius used for place search')
    network_type: str = Field(description='Road network mode used for area analysis')
    analysis_resource_id: str | None = Field(
        default=None, description='Underlying analysis_area resource identifier when available'
    )


class ObservationWindow(BaseModel):
    """A simplified best-observation window derived from hourly weather."""

    start_time: str | None = Field(
        default=None, description='Best hourly start time as an ISO string'
    )
    cloud_cover_percent: float | None = Field(
        default=None, description='Estimated cloud cover percent for the suggested hour'
    )
    precipitation_probability: float | None = Field(
        default=None, description='Estimated precipitation probability for the suggested hour'
    )
    wind_speed_kph: float | None = Field(
        default=None, description='Estimated wind speed in km/h for the suggested hour'
    )
    weather_text: str | None = Field(
        default=None, description='Human-readable weather summary for the suggested hour'
    )


class WeatherPlanningSummary(BaseModel):
    """Condensed weather fields used for location ranking and explanations."""

    weather_text: str | None = Field(
        default=None, description='Human-readable current weather text'
    )
    cloud_cover_percent: float | None = Field(
        default=None, description='Current total cloud cover percent'
    )
    visibility_km: float | None = Field(default=None, description='Current visibility in km')
    wind_speed_kph: float | None = Field(default=None, description='Current wind speed in km/h')


class PlanningTarget(BaseModel):
    """A compact target recommendation for the selected observing place."""

    name: str = Field(description='Target name')
    category: str = Field(description='Target category such as deep_sky or planet')
    score: float | None = Field(default=None, description='Target score when available')


class PlannedLocationCandidate(BaseModel):
    """A ranked location recommendation with weather and target context."""

    rank: int = Field(ge=1, description='Rank within the returned recommendation list')
    recommendation_score: float = Field(description='Combined planning score on a 0-100 scale')
    recommendation_reasons: list[str] = Field(
        default_factory=list, description='Short explanations for why this location is recommended'
    )
    location: StargazingLocation = Field(description='Candidate stargazing location')
    weather_summary: WeatherPlanningSummary | None = Field(
        default=None, description='Condensed weather context for this location'
    )
    best_observation_window: ObservationWindow | None = Field(
        default=None, description='Suggested best observation hour based on hourly weather'
    )
    moon_phase: str | None = Field(
        default=None, description='Moon phase label for the requested time'
    )
    moon_illumination: float | None = Field(
        default=None, description='Moon illumination fraction for the requested time'
    )
    top_targets: list[PlanningTarget] = Field(
        default_factory=list, description='Top astronomy targets for this location and time'
    )
    notes: list[str] = Field(
        default_factory=list, description='Supplementary notes about partial or missing data'
    )


class PlanningSummary(BaseModel):
    """High-level summary of the planning run."""

    generated_at: str = Field(description='Generation timestamp as an ISO string')
    requested_time: str = Field(description='Requested observation time string')
    time_zone: str = Field(description='Requested IANA timezone string')
    total_candidates: int = Field(ge=0, description='Number of ranked candidates returned')
    recommended_location_name: str | None = Field(
        default=None, description='Name of the top-ranked location when available'
    )
    warnings: list[str] = Field(
        default_factory=list, description='Plan-level warnings about partial downstream data'
    )


class BestStargazingPlan(BaseModel):
    """Top-level composite planning response."""

    query: PlanningQuery = Field(description='Normalized query parameters')
    summary: PlanningSummary = Field(description='High-level run summary')
    candidates: list[PlannedLocationCandidate] = Field(
        default_factory=list, description='Ranked recommended observing locations'
    )
