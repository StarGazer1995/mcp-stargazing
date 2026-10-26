"""Pydantic models for composite stargazing planning results."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from src.schemas.celestial import NightWindow
from src.schemas.places import StargazingLocation


class ObservationStyle(StrEnum):
    """Stable observer-goal profiles supported by the planning tool."""

    BALANCED = 'balanced'
    DEEP_SKY = 'deep_sky'
    VISUAL = 'visual'
    PLANETARY = 'planetary'
    BEGINNER = 'beginner'


class PlanningQuery(BaseModel):
    """Normalized query parameters for a composite planning request."""

    south: float = Field(description='Southern latitude bound')
    west: float = Field(description='Western longitude bound')
    north: float = Field(description='Northern latitude bound')
    east: float = Field(description='Eastern longitude bound')
    time: str = Field(description='Requested observation time string')
    time_zone: str = Field(description='Requested IANA timezone string')
    candidate_limit: int = Field(
        ge=1, description='Maximum number of ranked candidate places returned'
    )
    target_limit: int = Field(ge=1, description='Maximum number of recommended targets per place')
    weather_provider: str = Field(description='Weather provider mode used for weather summaries')
    max_locations: int = Field(
        ge=1, description='Maximum number of area-analysis candidates searched'
    )
    min_height_diff: float = Field(description='Minimum elevation difference used for place search')
    road_radius_km: float = Field(description='Road search radius used for place search')
    network_type: str = Field(description='Road network mode used for area analysis')
    observation_style: ObservationStyle = Field(
        default=ObservationStyle.BALANCED,
        description='Observer-goal profile used for scoring and target ordering',
    )
    avoid_popular_spots: bool = Field(
        default=False, description='Whether popularity risk was used to penalize place ranking'
    )
    prefer_quiet_at_night: bool = Field(
        default=False, description='Whether night quietness was used to influence place ranking'
    )
    popularity_radius_km: float = Field(
        default=3.0, gt=0, description='Preference horizon for popularity heuristics in km'
    )
    analysis_resource_id: str | None = Field(
        default=None, description='Underlying analysis_area resource identifier when available'
    )


class ObservationWindow(BaseModel):
    """A continuous observation window derived from hourly weather.

    ``start_time`` and the hourly weather fields are kept as the stable
    compatibility surface.  The range and quality fields are additive so
    callers can gradually move from a single best hour to a usable session
    window.
    """

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
    end_time: str | None = Field(
        default=None, description='Suggested observation end time as an ISO string'
    )
    duration_hours: float | None = Field(
        default=None, ge=0, description='Continuous observing duration represented by the window'
    )
    quality_score: float | None = Field(
        default=None, ge=0, le=100, description='Weather and observing quality score for the window'
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
    transit_alt: float | None = Field(
        default=None, description='Target culmination altitude in degrees when available'
    )


class RecommendationDriver(StrEnum):
    """Stable structured reasons behind a planning recommendation."""

    DARK_SKY = 'dark_sky'
    HIGH_PLACE_SCORE = 'high_place_score'
    CLEAR_WEATHER = 'clear_weather'
    GOOD_VISIBILITY = 'good_visibility'
    OBSERVATION_STYLE_FIT = 'observation_style_fit'
    LOW_POPULARITY_RISK = 'low_popularity_risk'
    QUIET_AT_NIGHT = 'quiet_at_night'
    STRONG_TARGETS = 'strong_targets'


class ScoreBreakdown(BaseModel):
    """Exact factors used to calculate a candidate's recommendation score."""

    place_base_score: float = Field(description='Underlying place score before weighting')
    place_weight: float = Field(description='Weight applied to the place score')
    place_contribution: float = Field(description='Weighted place-score contribution')
    weather_base_score: float = Field(description='Weather score after weather and moon penalties')
    weather_weight: float = Field(description='Weight applied to the weather score')
    weather_contribution: float = Field(description='Weighted weather-score contribution')
    popularity_adjustment: float = Field(
        description='Signed adjustment from explicit popularity preferences'
    )
    accessibility_adjustment: float = Field(
        description='Signed adjustment from beginner accessibility heuristics'
    )
    factor_contributions: dict[str, float] = Field(
        default_factory=dict,
        description=(
            'Signed score contributions keyed by the factors used for ranking; '
            'the keys are also used to select explanatory reasons'
        ),
    )
    final_score: float = Field(description='Final clamped recommendation score on a 0-100 scale')


class PlannedLocationCandidate(BaseModel):
    """A ranked location recommendation with weather and target context."""

    rank: int = Field(ge=1, description='Rank within the returned recommendation list')
    recommendation_score: float = Field(description='Combined planning score on a 0-100 scale')
    recommendation_reasons: list[str] = Field(
        default_factory=list, description='Short explanations for why this location is recommended'
    )
    score_breakdown: ScoreBreakdown | None = Field(
        default=None,
        description='Exact scoring components; absent only in older or externally supplied records',
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
    night_window: NightWindow | None = Field(
        default=None,
        description='Civil-dark observing window for this candidate when available',
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
    popularity_preferences_enabled: bool = Field(
        default=False,
        description=(
            'Whether popularity-aware preference flags were requested for planning-layer ranking'
        ),
    )
    primary_recommendation_drivers: list[RecommendationDriver] = Field(
        default_factory=list,
        description='Stable structured drivers behind the top recommendation, ordered by priority',
    )
    recommended_location_reason_summary: str | None = Field(
        default=None,
        description='Short human-readable summary of why the top location was recommended',
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


class MultiNightPlanningQuery(BaseModel):
    """Normalized query for a multi-night planning request."""

    south: float = Field(description='Southern latitude bound')
    west: float = Field(description='Western longitude bound')
    north: float = Field(description='Northern latitude bound')
    east: float = Field(description='Eastern longitude bound')
    start_date: str = Field(description='First local date in YYYY-MM-DD format')
    nights: int = Field(ge=1, le=7, description='Number of consecutive nights to evaluate')
    time_zone: str = Field(description='Requested IANA timezone string')
    observation_style: ObservationStyle = Field(
        default=ObservationStyle.BALANCED,
        description='Observer-goal profile used for every nightly plan',
    )


class NightlyStargazingPlan(BaseModel):
    """One night within a multi-night planning result."""

    night_index: int = Field(ge=1, description='One-based night sequence number')
    date: str = Field(description='Local date on which the night starts')
    night_window: NightWindow | None = Field(
        default=None, description='Civil-dark window for the regional center'
    )
    plan: BestStargazingPlan | None = Field(
        default=None, description='Nightly location ranking and explanations'
    )
    error: str | None = Field(default=None, description='Night-level failure reason')
    warnings: list[str] = Field(default_factory=list, description='Night-level warnings')


class MultiNightPlanningSummary(BaseModel):
    """Cross-night best result and degradation summary."""

    generated_at: str = Field(description='Generation timestamp as an ISO string')
    requested_nights: int = Field(ge=1, le=7, description='Number of nights requested')
    successful_nights: int = Field(ge=0, description='Nights with at least one candidate')
    best_night_index: int | None = Field(default=None, description='Best one-based night index')
    best_night_date: str | None = Field(default=None, description='Best local night date')
    best_location_name: str | None = Field(default=None, description='Best location across nights')
    best_score: float | None = Field(default=None, description='Best recommendation score')
    warnings: list[str] = Field(default_factory=list, description='Cross-night warnings')


class MultiNightStargazingPlan(BaseModel):
    """Top-level multi-night planning response."""

    query: MultiNightPlanningQuery = Field(description='Normalized multi-night query')
    summary: MultiNightPlanningSummary = Field(description='Cross-night summary')
    nights: list[NightlyStargazingPlan] = Field(
        default_factory=list, description='One entry per requested night'
    )
