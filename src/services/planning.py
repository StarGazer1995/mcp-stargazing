"""Application service for single-night and multi-night stargazing planning.

The service owns planning validation, orchestration, ranking, and explanation.
It depends on small async callables instead of MCP tool wrappers, which keeps
the public transport contract separate from application behavior.
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from src.response import MCPError
from src.schemas.agent_planning import (
    AgentPlanningAlternative,
    AgentPlanningDecision,
    AgentPlanningRequest,
    AgentPlanningResult,
    EquipmentPreset,
    EvidenceKind,
    PlanningChangeCondition,
    PlanningEvidence,
    PlanningMissingInput,
    PlanningNextAction,
    PlanningUncertainty,
    ResolvedEquipment,
    ResolvedPlanningLocation,
    UncertaintyLevel,
)
from src.schemas.base import GeoBounds, GeoPoint
from src.schemas.celestial import NightWindow
from src.schemas.places import StargazingLocation
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
    ScoreBreakdown,
    WeatherPlanningSummary,
)
from src.utils import (
    ensure_timezone,
    parse_observation_time,
    parse_time_string,
    validate_coordinates,
)

PlaceSearch = Callable[..., Awaitable[dict[str, Any]]]
WeatherFetch = Callable[..., Awaitable[dict[str, Any]]]
SpatialWeatherFetch = Callable[..., Awaitable[dict[str, Any]]]
ForecastFetch = Callable[..., Awaitable[dict[str, Any]]]
NightWindowFetch = Callable[[float, float, datetime], Awaitable[NightWindow]]
PlaceResolver = Callable[[str], Awaitable[Any]]
EquipmentTargetFetch = Callable[..., Awaitable[dict[str, Any]]]
Clock = Callable[[], datetime]


@dataclass(frozen=True)
class PlanningDependencies:
    """External capabilities required by :class:`PlanningService`."""

    search_places: PlaceSearch
    fetch_weather: WeatherFetch
    fetch_forecast: ForecastFetch
    fetch_night_window: NightWindowFetch
    now: Clock
    resolve_place: PlaceResolver | None = None
    fetch_equipment_targets: EquipmentTargetFetch | None = None
    fetch_spatial_weather: SpatialWeatherFetch | None = None


@dataclass(frozen=True)
class _ObservationStyleProfile:
    place_weight: float
    weather_weight: float
    moon_penalty_multiplier: float
    reason: str | None


@dataclass(frozen=True)
class _WeatherScreen:
    """Cheap weather result reused by the downstream candidate evaluator."""

    data: dict[str, Any] | None
    note: str | None
    spatial_cloud_cover_percent: float | None = None


_STYLE_PROFILES = {
    ObservationStyle.BALANCED: _ObservationStyleProfile(0.65, 0.35, 1.0, None),
    ObservationStyle.DEEP_SKY: _ObservationStyleProfile(
        0.72, 0.28, 1.15, '深空摄影偏好提高了暗空与低月光条件的权重。'
    ),
    ObservationStyle.VISUAL: _ObservationStyleProfile(
        0.55, 0.45, 0.45, '目视观测偏好提高了实时天气权重并降低月光影响。'
    ),
    ObservationStyle.PLANETARY: _ObservationStyleProfile(
        0.42, 0.58, 0.08, '行星观测偏好显著降低月光惩罚并优先安排行星目标。'
    ),
    ObservationStyle.BEGINNER: _ObservationStyleProfile(
        0.60, 0.40, 0.25, '入门观测偏好兼顾天气、地点评分与交通便利性。'
    ),
}

_EQUIPMENT_PRESETS: dict[EquipmentPreset, dict[str, Any]] = {
    EquipmentPreset.SEESTAR_S50: {
        'focal_length_mm': 250.0,
        'aperture_mm': 50.0,
        'sensor_pixel_size_um': 2.9,
        'mount_type': 'altaz',
    },
    EquipmentPreset.HOPE_D60_ASI2600MC_AIR: {
        'focal_length_mm': 280.0,
        'aperture_mm': 60.0,
        'sensor_width_mm': 23.5,
        'sensor_height_mm': 15.7,
        'sensor_pixel_size_um': 3.76,
        'mount_type': 'equatorial',
    },
}

# Keep the public result small while allowing weather and target signals to
# overturn a purely static place ranking. ``max_locations`` remains the caller's
# search budget; this cap only limits how many returned places receive the more
# expensive downstream evaluation.
_LOCATION_RECALL_MULTIPLIER = 5
_MIN_LOCATION_RECALL = 10
_TARGET_EVALUATION_MULTIPLIER = 2
_MIN_TARGET_EVALUATIONS = 3
_SPATIAL_CLOUD_BLEND = 0.3


def _location_recall_limit(candidate_limit: int, max_locations: int) -> int:
    """Return the number of places to evaluate before final score truncation."""

    return min(
        max_locations,
        max(_MIN_LOCATION_RECALL, candidate_limit * _LOCATION_RECALL_MULTIPLIER),
    )


def _target_evaluation_limit(candidate_limit: int, screened_count: int) -> int:
    """Bound expensive target evaluation after the weather pre-screen."""

    return min(
        screened_count,
        max(_MIN_TARGET_EVALUATIONS, candidate_limit * _TARGET_EVALUATION_MULTIPLIER),
    )


def _validate_observation_style(value: str) -> ObservationStyle:
    try:
        return ObservationStyle(value)
    except ValueError as exc:
        allowed = ', '.join(style.value for style in ObservationStyle)
        raise MCPError(
            MCPError.CONFIGURATION_ERROR,
            f'observation_style must be one of: {allowed}.',
            {'observation_style': value},
        ) from exc


def _validate_bounds(south: float, west: float, north: float, east: float) -> None:
    if not validate_coordinates(south, west) or not validate_coordinates(north, east):
        raise MCPError(
            MCPError.INVALID_COORDINATES,
            'Bounding box contains invalid coordinates.',
            {'south': south, 'west': west, 'north': north, 'east': east},
        )
    if south >= north:
        raise MCPError(
            MCPError.CONFIGURATION_ERROR,
            'south must be less than north.',
            {'south': south, 'north': north},
        )
    if west >= east:
        raise MCPError(
            MCPError.CONFIGURATION_ERROR,
            'west must be less than east.',
            {'west': west, 'east': east},
        )


def _validate_positive_int(name: str, value: int) -> None:
    if value < 1:
        raise MCPError(
            MCPError.CONFIGURATION_ERROR,
            f'{name} must be greater than or equal to 1.',
            {name: value},
        )


def _pick_best_observation_window(
    hourly_items: list[dict[str, Any]],
    requested_time: str,
    time_zone: str,
    *,
    night_window: NightWindow | None = None,
    moon_illumination: float | None = None,
    top_targets: list[PlanningTarget] | None = None,
) -> ObservationWindow | None:
    if not hourly_items:
        return None

    requested_dt = parse_observation_time(requested_time, time_zone)
    cutoff_dt = requested_dt + timedelta(hours=12)
    dark_start = dark_end = None
    if night_window is not None:
        try:
            dark_start = ensure_timezone(parse_time_string(night_window.civil_dusk), time_zone)
            dark_end = ensure_timezone(parse_time_string(night_window.civil_dawn), time_zone)
        except (MCPError, TypeError, ValueError):
            dark_start = dark_end = None

    target_altitudes = [
        float(target.transit_alt) for target in top_targets or [] if target.transit_alt is not None
    ]
    target_altitude_bonus = min(10.0, max(0.0, (max(target_altitudes, default=0.0) - 20.0) * 0.2))

    def score_item(item: dict[str, Any]) -> float:
        score = 100.0
        cloud_cover = item.get('cloud_cover_percent')
        precipitation = item.get('precipitation_probability')
        wind_speed = item.get('wind_speed_kph')
        if cloud_cover is not None:
            score -= float(cloud_cover) * 0.7
        if precipitation is not None:
            score -= float(precipitation) * 20.0
        if wind_speed is not None and float(wind_speed) > 20.0:
            score -= (float(wind_speed) - 20.0) * 1.5
        if moon_illumination is not None and moon_illumination > 0.7:
            score -= (moon_illumination - 0.7) * 20.0
        return max(0.0, min(100.0, score + target_altitude_bonus))

    records: list[tuple[datetime, dict[str, Any], float]] = []
    for item in hourly_items:
        time_value = item.get('time')
        if not time_value:
            continue
        try:
            forecast_dt = ensure_timezone(parse_time_string(time_value), time_zone)
        except (MCPError, TypeError, ValueError):
            continue
        if forecast_dt < requested_dt or forecast_dt > cutoff_dt:
            continue
        if (
            dark_start is not None
            and dark_end is not None
            and not (dark_start <= forecast_dt <= dark_end)
        ):
            continue
        records.append((forecast_dt, item, score_item(item)))

    if not records:
        return None
    records.sort(key=lambda record: record[0])

    def is_usable(item: dict[str, Any]) -> bool:
        cloud_cover = item.get('cloud_cover_percent')
        precipitation = item.get('precipitation_probability')
        wind_speed = item.get('wind_speed_kph')
        return (
            (cloud_cover is None or float(cloud_cover) <= 75.0)
            and (precipitation is None or float(precipitation) <= 0.35)
            and (wind_speed is None or float(wind_speed) <= 35.0)
        )

    runs: list[list[tuple[datetime, dict[str, Any], float]]] = []
    current_run: list[tuple[datetime, dict[str, Any], float]] = []
    for record in records:
        if not is_usable(record[1]):
            if current_run:
                runs.append(current_run)
                current_run = []
            continue
        if current_run and record[0] - current_run[-1][0] > timedelta(minutes=90):
            runs.append(current_run)
            current_run = []
        current_run.append(record)
    if current_run:
        runs.append(current_run)

    if runs:
        selected_run = max(
            runs,
            key=lambda run: (
                sum(record[2] for record in run) / len(run),
                (run[-1][0] - run[0][0]).total_seconds(),
                -run[0][0].timestamp(),
            ),
        )
    else:
        selected_run = [max(records, key=lambda record: (record[2], -record[0].timestamp()))]

    first_dt, best_item, _ = selected_run[0]
    last_dt = selected_run[-1][0]
    duration_hours = max(1.0, round((last_dt - first_dt).total_seconds() / 3600.0 + 1.0, 2))
    end_time = (last_dt + timedelta(hours=1)).isoformat()
    quality_score = round(
        sum(record[2] for record in selected_run) / len(selected_run),
        2,
    )
    return ObservationWindow(
        start_time=best_item.get('time'),
        cloud_cover_percent=best_item.get('cloud_cover_percent'),
        precipitation_probability=best_item.get('precipitation_probability'),
        wind_speed_kph=best_item.get('wind_speed_kph'),
        weather_text=best_item.get('weather_text'),
        end_time=end_time,
        duration_hours=duration_hours,
        quality_score=quality_score,
    )


def _build_weather_summary(weather_data: dict[str, Any] | None) -> WeatherPlanningSummary | None:
    if weather_data is None:
        return None
    current = weather_data.get('summary', {}).get('current', {})
    return WeatherPlanningSummary(
        weather_text=current.get('weather_text'),
        cloud_cover_percent=current.get('cloud_cover_percent'),
        visibility_km=current.get('visibility_km'),
        wind_speed_kph=current.get('wind_speed_kph'),
    )


def _build_top_targets(
    forecast_data: dict[str, Any] | None,
    target_limit: int,
    observation_style: ObservationStyle,
) -> list[PlanningTarget]:
    if forecast_data is None:
        return []
    targets: list[PlanningTarget] = []
    sources = (
        (forecast_data.get('planets', []), 'planet'),
        (forecast_data.get('deep_sky', []), 'deep_sky'),
    )
    if observation_style in {ObservationStyle.BALANCED, ObservationStyle.DEEP_SKY}:
        sources = tuple(reversed(sources))
    for items, fallback_category in sources:
        for item in items:
            if len(targets) >= target_limit:
                return targets
            targets.append(
                PlanningTarget(
                    name=item['name'],
                    category=(
                        fallback_category
                        if fallback_category == 'planet'
                        else item.get('type', 'deep_sky')
                    ),
                    score=item.get('score'),
                    transit_alt=item.get('transit_alt'),
                )
            )
    return targets


def _compute_recommendation_score(
    location: StargazingLocation,
    weather_summary: WeatherPlanningSummary | None,
    best_window: ObservationWindow | None,
    moon_illumination: float | None,
    observation_style: ObservationStyle,
    popularity_adjustment: float,
    spatial_cloud_cover_percent: float | None = None,
) -> ScoreBreakdown:
    profile = _STYLE_PROFILES[observation_style]
    weather_score = 55.0
    if weather_summary is not None:
        if weather_summary.cloud_cover_percent is not None:
            weather_score = max(0.0, 100.0 - float(weather_summary.cloud_cover_percent))
        if weather_summary.visibility_km is not None:
            weather_score += min(20.0, float(weather_summary.visibility_km) * 1.5)
        if weather_summary.wind_speed_kph is not None and weather_summary.wind_speed_kph > 20.0:
            weather_score -= min(20.0, (float(weather_summary.wind_speed_kph) - 20.0) * 1.2)
    if best_window is not None and best_window.precipitation_probability is not None:
        weather_score -= float(best_window.precipitation_probability) * 20.0
    if best_window is not None and best_window.duration_hours is not None:
        weather_score += min(12.0, max(0.0, best_window.duration_hours - 1.0) * 2.0)
    if spatial_cloud_cover_percent is not None and math.isfinite(spatial_cloud_cover_percent):
        spatial_cloud_score = 100.0 - max(0.0, min(100.0, spatial_cloud_cover_percent))
        weather_score = (
            weather_score * (1.0 - _SPATIAL_CLOUD_BLEND)
            + spatial_cloud_score * _SPATIAL_CLOUD_BLEND
        )
    if moon_illumination is not None and moon_illumination > 0.7:
        weather_score -= (moon_illumination - 0.7) * 25.0 * profile.moon_penalty_multiplier
    place_score = float(location.score or 0.0)
    normalized_weather_score = max(0.0, weather_score)
    place_contribution = place_score * profile.place_weight
    weather_contribution = normalized_weather_score * profile.weather_weight
    accessibility_adjustment = 0.0
    combined = place_contribution + weather_contribution + popularity_adjustment
    if observation_style == ObservationStyle.BEGINNER and location.road_distance_km is not None:
        if location.road_distance_km <= 5.0:
            accessibility_adjustment = 3.0
        elif location.road_distance_km > 20.0:
            accessibility_adjustment = -3.0
    combined += accessibility_adjustment
    final_score = round(max(0.0, min(100.0, combined)), 2)
    return ScoreBreakdown(
        place_base_score=round(place_score, 2),
        place_weight=profile.place_weight,
        place_contribution=round(place_contribution, 2),
        weather_base_score=round(normalized_weather_score, 2),
        weather_weight=profile.weather_weight,
        weather_contribution=round(weather_contribution, 2),
        popularity_adjustment=round(popularity_adjustment, 2),
        accessibility_adjustment=round(accessibility_adjustment, 2),
        factor_contributions={
            'place_score': round(place_contribution, 2),
            'weather': round(weather_contribution, 2),
            'popularity_preferences': round(popularity_adjustment, 2),
            'accessibility': round(accessibility_adjustment, 2),
        },
        final_score=final_score,
    )


def _compute_popularity_preference_adjustment(
    location: StargazingLocation,
    avoid_popular_spots: bool,
    prefer_quiet_at_night: bool,
    popularity_radius_km: float,
) -> tuple[float, list[str]]:
    if not avoid_popular_spots and not prefer_quiet_at_night:
        return 0.0, []
    radius_factor = max(0.5, min(1.5, popularity_radius_km / 3.0))
    adjustment = 0.0
    reasons: list[str] = []
    if avoid_popular_spots and location.static_popularity_risk_score is not None:
        risk_score = float(location.static_popularity_risk_score)
        adjustment += (50.0 - risk_score) / 50.0 * 7.0 * radius_factor
        if risk_score <= 35.0:
            reasons.append(f'静态热门风险约 {risk_score:.0f}/100，更符合避开热门点偏好。')
        elif risk_score >= 65.0:
            reasons.append(f'静态热门风险约 {risk_score:.0f}/100，已按偏好下调优先级。')
    if prefer_quiet_at_night and location.night_quiet_likelihood_score is not None:
        quiet_score = float(location.night_quiet_likelihood_score)
        confidence = float(location.temporal_popularity_confidence or 50.0)
        confidence_factor = max(0.35, min(1.0, confidence / 100.0))
        adjustment += (quiet_score - 50.0) / 50.0 * 7.0 * confidence_factor * radius_factor
        if quiet_score >= 65.0:
            reasons.append(
                f'夜间安静概率约 {quiet_score:.0f}/100'
                f'（置信度 {confidence:.0f}/100），更贴合夜间安静偏好。'
            )
        elif quiet_score <= 35.0:
            reasons.append(f'夜间持续活跃概率偏高，夜间安静概率仅约 {quiet_score:.0f}/100。')
    if location.popularity_notes and len(reasons) < 2:
        reasons.append(location.popularity_notes)
    return round(adjustment, 2), reasons[:2]


def _build_recommendation_reasons(
    location: StargazingLocation,
    weather_summary: WeatherPlanningSummary | None,
    best_window: ObservationWindow | None,
    moon_illumination: float | None,
    top_targets: list[PlanningTarget],
    observation_style: ObservationStyle,
    popularity_reasons: list[str],
    score_breakdown: ScoreBreakdown | None = None,
    spatial_cloud_cover_percent: float | None = None,
) -> list[str]:
    reason_entries: list[tuple[int, str]] = []
    if location.bortle_class is not None:
        reason_entries.append((1000, f'波特尔等级约为 {location.bortle_class}，暗空条件较清晰。'))
    elif location.score is not None:
        reason_entries.append((1000, f'地点基础观星评分为 {location.score:.1f}。'))
    if _STYLE_PROFILES[observation_style].reason:
        reason_entries.append((650, _STYLE_PROFILES[observation_style].reason))
    reason_entries.extend((900, reason) for reason in popularity_reasons)
    if weather_summary is not None and weather_summary.cloud_cover_percent is not None:
        reason_entries.append((800, f'当前云量约 {weather_summary.cloud_cover_percent:.0f}%。'))
    if weather_summary is not None and weather_summary.visibility_km is not None:
        reason_entries.append((800, f'当前能见度约 {weather_summary.visibility_km:.1f} km。'))
    if weather_summary is not None and weather_summary.wind_speed_kph is not None:
        if weather_summary.wind_speed_kph > 20.0:
            reason_entries.append(
                (
                    850,
                    f'当前风速约 {weather_summary.wind_speed_kph:.1f} km/h，已计入天气扣分。',
                )
            )
    if best_window is not None and best_window.start_time is not None:
        if best_window.end_time is not None and best_window.duration_hours is not None:
            reason_entries.append(
                (
                    860,
                    f'建议在 {best_window.start_time} 至 {best_window.end_time} '
                    f'连续观测（约 {best_window.duration_hours:.1f} 小时）。',
                )
            )
        else:
            reason_entries.append((860, f'建议优先在 {best_window.start_time} 附近观测。'))
        if (
            best_window.precipitation_probability is not None
            and best_window.precipitation_probability > 0
        ):
            reason_entries.append(
                (
                    850,
                    f'窗口降水概率约 {best_window.precipitation_probability:.0%}，已计入天气扣分。',
                )
            )
    if spatial_cloud_cover_percent is not None and math.isfinite(spatial_cloud_cover_percent):
        reason_entries.append(
            (
                880,
                f'区域空间云量约 {spatial_cloud_cover_percent:.0f}%，已用于区域比较。',
            )
        )
    if moon_illumination is not None and moon_illumination > 0.7:
        reason_entries.append(
            (
                850,
                f'月面照明比例约为 {moon_illumination:.0%}，已按观测风格计入月光惩罚。',
            )
        )
    if (
        score_breakdown is not None
        and score_breakdown.factor_contributions.get('accessibility', 0.0) != 0.0
        and location.road_distance_km is not None
    ):
        reason_entries.append(
            (
                840,
                f'道路距离约 {location.road_distance_km:.1f} km，已计入入门观测便利性调整。',
            )
        )
    if top_targets:
        reason_entries.append(
            (100, f'优先目标包括 {", ".join(target.name for target in top_targets[:3])}。')
        )
    reason_entries.sort(key=lambda item: item[0], reverse=True)
    return [reason for _priority, reason in reason_entries[:5]]


def _derive_primary_recommendation_drivers(
    candidate: PlannedLocationCandidate | None,
    avoid_popular_spots: bool,
    prefer_quiet_at_night: bool,
    observation_style: ObservationStyle,
) -> list[RecommendationDriver]:
    if candidate is None:
        return []
    drivers: list[RecommendationDriver] = []
    location = candidate.location
    weather_summary = candidate.weather_summary
    if location.bortle_class is not None and location.bortle_class <= 4:
        drivers.append(RecommendationDriver.DARK_SKY)
    elif location.score is not None and float(location.score) >= 80.0:
        drivers.append(RecommendationDriver.HIGH_PLACE_SCORE)
    if weather_summary is not None:
        if (
            weather_summary.cloud_cover_percent is not None
            and weather_summary.cloud_cover_percent <= 25
        ):
            drivers.append(RecommendationDriver.CLEAR_WEATHER)
        elif weather_summary.visibility_km is not None and weather_summary.visibility_km >= 15:
            drivers.append(RecommendationDriver.GOOD_VISIBILITY)
    if observation_style != ObservationStyle.BALANCED:
        drivers.append(RecommendationDriver.OBSERVATION_STYLE_FIT)
    if (
        avoid_popular_spots
        and location.static_popularity_risk_score is not None
        and location.static_popularity_risk_score <= 35
    ):
        drivers.append(RecommendationDriver.LOW_POPULARITY_RISK)
    if (
        prefer_quiet_at_night
        and location.night_quiet_likelihood_score is not None
        and location.night_quiet_likelihood_score >= 65
    ):
        drivers.append(RecommendationDriver.QUIET_AT_NIGHT)
    if candidate.top_targets:
        drivers.append(RecommendationDriver.STRONG_TARGETS)
    return drivers[:4]


def _build_recommended_location_reason_summary(
    candidate: PlannedLocationCandidate | None,
    primary_drivers: list[RecommendationDriver],
) -> str | None:
    if candidate is None:
        return None
    labels = {
        RecommendationDriver.DARK_SKY: '暗空条件更好',
        RecommendationDriver.HIGH_PLACE_SCORE: '地点基础评分更高',
        RecommendationDriver.CLEAR_WEATHER: '天气更晴朗',
        RecommendationDriver.GOOD_VISIBILITY: '能见度更好',
        RecommendationDriver.OBSERVATION_STYLE_FIT: '观测目标偏好匹配',
        RecommendationDriver.LOW_POPULARITY_RISK: '热门度风险更低',
        RecommendationDriver.QUIET_AT_NIGHT: '夜间更安静',
        RecommendationDriver.STRONG_TARGETS: '可观测目标更强',
    }
    if primary_drivers:
        summary = '、'.join(labels[driver] for driver in primary_drivers[:3])
        return f'{candidate.location.name} 当前主要因{summary}而成为首选。'
    if candidate.recommendation_reasons:
        return candidate.recommendation_reasons[0]
    return None


def _bounds_from_center(center: GeoPoint, radius_km: float) -> GeoBounds:
    """Build an approximate search box around a WGS84 center point."""

    latitude_delta = radius_km / 111.32
    longitude_scale = max(0.01, math.cos(math.radians(center.lat)))
    longitude_delta = radius_km / (111.32 * longitude_scale)
    south = max(-90.0, center.lat - latitude_delta)
    north = min(90.0, center.lat + latitude_delta)
    west = center.lon - longitude_delta
    east = center.lon + longitude_delta
    if west < -180.0 or east > 180.0:
        raise MCPError(
            MCPError.CONFIGURATION_ERROR,
            'The requested center/radius crosses the antimeridian; provide exact bounds instead.',
            {'lat': center.lat, 'lon': center.lon, 'radius_km': radius_km},
        )
    return GeoBounds(south=south, west=west, north=north, east=east)


def _resolve_equipment(request: AgentPlanningRequest) -> ResolvedEquipment | None:
    """Resolve a stable equipment preset and apply explicit caller overrides."""

    if request.equipment is None:
        return None
    if request.equipment.preset == EquipmentPreset.CUSTOM:
        values: dict[str, Any] = {}
    else:
        values = dict(_EQUIPMENT_PRESETS[request.equipment.preset])
    values.update(request.equipment.overrides.model_dump(exclude_none=True))
    return ResolvedEquipment(preset=request.equipment.preset, **values)


def _score_comparison(decision: ScoreBreakdown, alternative: ScoreBreakdown) -> dict[str, float]:
    """Return signed alternative-minus-decision component differences."""

    return {
        'place_contribution': round(
            alternative.place_contribution - decision.place_contribution, 2
        ),
        'weather_contribution': round(
            alternative.weather_contribution - decision.weather_contribution, 2
        ),
        'popularity_adjustment': round(
            alternative.popularity_adjustment - decision.popularity_adjustment, 2
        ),
        'accessibility_adjustment': round(
            alternative.accessibility_adjustment - decision.accessibility_adjustment, 2
        ),
    }


class PlanningService:
    """Plan observing sessions without depending on MCP wrappers or transport."""

    def __init__(self, dependencies: PlanningDependencies):
        self._dependencies = dependencies

    async def _fetch_optional(self, operation: Awaitable[dict[str, Any]]):
        try:
            return await operation, None
        except MCPError as exc:
            return None, f'{exc.code}: {exc.message}'
        except Exception as exc:
            return None, f'{MCPError.EXTERNAL_API_ERROR}: {exc}'

    async def _screen_weather(
        self, location: StargazingLocation, weather_provider: str
    ) -> _WeatherScreen:
        """Fetch only the inexpensive weather summary for a recall candidate."""

        data, note = await self._fetch_optional(
            self._dependencies.fetch_weather(
                lat=location.lat, lon=location.lon, provider=weather_provider
            )
        )
        return _WeatherScreen(data=data, note=note)

    async def evaluate_candidate(
        self,
        location: StargazingLocation,
        time: str,
        time_zone: str,
        target_limit: int,
        weather_provider: str,
        observation_style: ObservationStyle = ObservationStyle.BALANCED,
        avoid_popular_spots: bool = False,
        prefer_quiet_at_night: bool = False,
        popularity_radius_km: float = 3.0,
        *,
        prefetched_weather: _WeatherScreen | None = None,
    ) -> PlannedLocationCandidate:
        notes: list[str] = []
        reference = parse_observation_time(time, time_zone)
        try:
            night_window = await self._dependencies.fetch_night_window(
                location.lat, location.lon, reference
            )
        except ValueError as exc:
            night_window = None
            notes.append(f'夜景窗口不可用：{exc}')
        forecast_operation = self._fetch_optional(
            self._dependencies.fetch_forecast(
                lon=location.lon,
                lat=location.lat,
                time=time,
                time_zone=time_zone,
                limit=target_limit,
            )
        )
        if prefetched_weather is None:
            weather_result, forecast_result = await asyncio.gather(
                self._fetch_optional(
                    self._dependencies.fetch_weather(
                        lat=location.lat, lon=location.lon, provider=weather_provider
                    )
                ),
                forecast_operation,
            )
        else:
            weather_result = (prefetched_weather.data, prefetched_weather.note)
            forecast_result = await forecast_operation
        weather_data, weather_note = weather_result
        forecast_data, forecast_note = forecast_result
        if weather_note:
            notes.append(f'天气摘要降级处理：{weather_note}')
        if (
            prefetched_weather is not None
            and prefetched_weather.spatial_cloud_cover_percent is not None
        ):
            notes.append(
                '区域空间天气参考云量约 '
                f'{prefetched_weather.spatial_cloud_cover_percent:.0f}%，已用于区域比较。'
            )
        if forecast_note:
            notes.append(f'夜间目标降级处理：{forecast_note}')
        weather_summary = _build_weather_summary(weather_data)
        top_targets = _build_top_targets(forecast_data, target_limit, observation_style)
        moon_phase = None
        moon_illumination = None
        if forecast_data is not None:
            moon_phase = forecast_data.get('moon_phase', {}).get('phase_name')
            moon_illumination = forecast_data.get('moon_phase', {}).get('illumination')
        best_window = None
        if weather_data is not None:
            best_window = _pick_best_observation_window(
                weather_data.get('summary', {}).get('hourly', []),
                time,
                time_zone,
                night_window=night_window,
                moon_illumination=moon_illumination,
                top_targets=top_targets,
            )
        popularity_adjustment, popularity_reasons = _compute_popularity_preference_adjustment(
            location, avoid_popular_spots, prefer_quiet_at_night, popularity_radius_km
        )
        score_breakdown = _compute_recommendation_score(
            location,
            weather_summary,
            best_window,
            moon_illumination,
            observation_style,
            popularity_adjustment,
            prefetched_weather.spatial_cloud_cover_percent if prefetched_weather else None,
        )
        reasons = _build_recommendation_reasons(
            location,
            weather_summary,
            best_window,
            moon_illumination,
            top_targets,
            observation_style,
            popularity_reasons,
            score_breakdown,
            prefetched_weather.spatial_cloud_cover_percent if prefetched_weather else None,
        )
        return PlannedLocationCandidate(
            rank=1,
            recommendation_score=score_breakdown.final_score,
            recommendation_reasons=reasons,
            score_breakdown=score_breakdown,
            location=location,
            weather_summary=weather_summary,
            best_observation_window=best_window,
            moon_phase=moon_phase,
            moon_illumination=moon_illumination,
            night_window=night_window,
            top_targets=top_targets,
            notes=notes,
        )

    async def build_best_plan(
        self,
        *,
        south: float,
        west: float,
        north: float,
        east: float,
        time: str,
        time_zone: str,
        candidate_limit: int = 3,
        target_limit: int = 5,
        weather_provider: str = 'all',
        max_locations: int = 10,
        min_height_diff: float = 100.0,
        road_radius_km: float = 10.0,
        network_type: str = 'drive',
        observation_style: str = 'balanced',
        avoid_popular_spots: bool = False,
        prefer_quiet_at_night: bool = False,
        popularity_radius_km: float = 3.0,
        db_config_path: str | None = None,
    ) -> BestStargazingPlan:
        _validate_bounds(south, west, north, east)
        _validate_positive_int('candidate_limit', candidate_limit)
        _validate_positive_int('target_limit', target_limit)
        _validate_positive_int('max_locations', max_locations)
        style = _validate_observation_style(observation_style)
        if popularity_radius_km <= 0:
            raise MCPError(
                MCPError.CONFIGURATION_ERROR,
                'popularity_radius_km must be greater than 0.',
                {'popularity_radius_km': popularity_radius_km},
            )
        parse_observation_time(time, time_zone)
        places_data = await self._dependencies.search_places(
            south=south,
            west=west,
            north=north,
            east=east,
            max_locations=max_locations,
            min_height_diff=min_height_diff,
            road_radius_km=road_radius_km,
            network_type=network_type,
            avoid_popular_spots=avoid_popular_spots,
            prefer_quiet_at_night=prefer_quiet_at_night,
            popularity_radius_km=popularity_radius_km,
            db_config_path=db_config_path,
            page=1,
            page_size=max_locations,
        )
        recall_limit = _location_recall_limit(candidate_limit, max_locations)
        locations = [
            StargazingLocation(**item) for item in places_data.get('items', [])[:recall_limit]
        ]
        weather_screens = await asyncio.gather(
            *[self._screen_weather(location, weather_provider) for location in locations]
        )
        spatial_data: dict[str, Any] | None = None
        spatial_note: str | None = None
        if self._dependencies.fetch_spatial_weather is not None and locations:
            spatial_data, spatial_note = await self._fetch_optional(
                self._dependencies.fetch_spatial_weather(
                    south=south,
                    west=west,
                    north=north,
                    east=east,
                    time=time,
                    time_zone=time_zone,
                    locations=[
                        {'lat': location.lat, 'lon': location.lon} for location in locations
                    ],
                )
            )
        spatial_samples = (spatial_data or {}).get('samples', [])
        screened_candidates: list[tuple[float, StargazingLocation, _WeatherScreen]] = []
        for index, (location, weather_screen) in enumerate(
            zip(locations, weather_screens, strict=True)
        ):
            spatial_cloud = None
            if index < len(spatial_samples) and isinstance(spatial_samples[index], dict):
                raw_cloud = spatial_samples[index].get('cloud_cover_percent')
                if isinstance(raw_cloud, (int, float)) and math.isfinite(raw_cloud):
                    spatial_cloud = float(raw_cloud)
            weather_screen = _WeatherScreen(
                data=weather_screen.data,
                note=weather_screen.note,
                spatial_cloud_cover_percent=spatial_cloud,
            )
            weather_summary = _build_weather_summary(weather_screen.data)
            best_window = None
            if weather_screen.data is not None:
                best_window = _pick_best_observation_window(
                    weather_screen.data.get('summary', {}).get('hourly', []), time, time_zone
                )
            popularity_adjustment, _ = _compute_popularity_preference_adjustment(
                location, avoid_popular_spots, prefer_quiet_at_night, popularity_radius_km
            )
            screen_score = _compute_recommendation_score(
                location,
                weather_summary,
                best_window,
                None,
                style,
                popularity_adjustment,
                spatial_cloud,
            ).final_score
            screened_candidates.append((screen_score, location, weather_screen))
        screened_candidates.sort(key=lambda item: item[0], reverse=True)
        target_evaluation_limit = _target_evaluation_limit(
            candidate_limit, len(screened_candidates)
        )
        evaluated_candidates = await asyncio.gather(
            *[
                self.evaluate_candidate(
                    location,
                    time,
                    time_zone,
                    target_limit,
                    weather_provider,
                    style,
                    avoid_popular_spots,
                    prefer_quiet_at_night,
                    popularity_radius_km,
                    prefetched_weather=weather_screen,
                )
                for _screen_score, location, weather_screen in screened_candidates[
                    :target_evaluation_limit
                ]
            ]
        )
        ranked_candidates = sorted(
            evaluated_candidates, key=lambda item: item.recommendation_score, reverse=True
        )
        candidates = ranked_candidates[:candidate_limit]
        for rank, candidate in enumerate(candidates, start=1):
            candidate.rank = rank
        top_candidate = candidates[0] if candidates else None
        drivers = _derive_primary_recommendation_drivers(
            top_candidate, avoid_popular_spots, prefer_quiet_at_night, style
        )
        warning_notes = {note for candidate in candidates for note in candidate.notes}
        if spatial_note:
            warning_notes.add(f'空间天气粗排降级处理：{spatial_note}')
        warnings = sorted(warning_notes)
        return BestStargazingPlan(
            query=PlanningQuery(
                south=south,
                west=west,
                north=north,
                east=east,
                time=time,
                time_zone=time_zone,
                candidate_limit=candidate_limit,
                target_limit=target_limit,
                weather_provider=weather_provider,
                max_locations=max_locations,
                min_height_diff=min_height_diff,
                road_radius_km=road_radius_km,
                network_type=network_type,
                observation_style=style,
                avoid_popular_spots=avoid_popular_spots,
                prefer_quiet_at_night=prefer_quiet_at_night,
                popularity_radius_km=popularity_radius_km,
                analysis_resource_id=places_data.get('resource_id'),
            ),
            summary=PlanningSummary(
                generated_at=self._dependencies.now().isoformat(),
                requested_time=time,
                time_zone=time_zone,
                total_candidates=len(candidates),
                recommended_location_name=top_candidate.location.name if top_candidate else None,
                popularity_preferences_enabled=avoid_popular_spots or prefer_quiet_at_night,
                primary_recommendation_drivers=drivers,
                recommended_location_reason_summary=(
                    _build_recommended_location_reason_summary(top_candidate, drivers)
                ),
                warnings=warnings,
            ),
            candidates=candidates,
        )

    async def build_multiday_plan(
        self,
        *,
        south: float,
        west: float,
        north: float,
        east: float,
        start_date: str,
        time_zone: str,
        nights: int = 3,
        candidate_limit: int = 3,
        target_limit: int = 5,
        weather_provider: str = 'all',
        max_locations: int = 10,
        min_height_diff: float = 100.0,
        road_radius_km: float = 10.0,
        network_type: str = 'drive',
        observation_style: str = 'balanced',
        avoid_popular_spots: bool = False,
        prefer_quiet_at_night: bool = False,
        popularity_radius_km: float = 3.0,
        db_config_path: str | None = None,
    ) -> MultiNightStargazingPlan:
        _validate_bounds(south, west, north, east)
        if nights < 1 or nights > 7:
            raise MCPError(
                MCPError.CONFIGURATION_ERROR,
                'nights must be between 1 and 7.',
                {'nights': nights},
            )
        _validate_positive_int('candidate_limit', candidate_limit)
        _validate_positive_int('target_limit', target_limit)
        _validate_positive_int('max_locations', max_locations)
        style = _validate_observation_style(observation_style)
        if popularity_radius_km <= 0:
            raise MCPError(
                MCPError.CONFIGURATION_ERROR,
                'popularity_radius_km must be greater than 0.',
                {'popularity_radius_km': popularity_radius_km},
            )
        start_noon = parse_observation_time(f'{start_date} 12:00:00', time_zone)
        center_lat = (south + north) / 2.0
        center_lon = (west + east) / 2.0
        night_results: list[NightlyStargazingPlan] = []
        for night_index in range(1, nights + 1):
            reference = start_noon + timedelta(days=night_index - 1)
            local_date = reference.date().isoformat()
            try:
                window = await self._dependencies.fetch_night_window(
                    center_lat, center_lon, reference
                )
            except ValueError as exc:
                night_results.append(
                    NightlyStargazingPlan(
                        night_index=night_index,
                        date=local_date,
                        error=f'无法确定当晚民用暗夜窗口：{exc}',
                        warnings=['night_window_unavailable'],
                    )
                )
                continue
            dusk = datetime.fromisoformat(window.civil_dusk)
            dawn = datetime.fromisoformat(window.civil_dawn)
            planning_time = dusk + (dawn - dusk) / 2.0
            try:
                plan = await self.build_best_plan(
                    south=south,
                    west=west,
                    north=north,
                    east=east,
                    time=planning_time.strftime('%Y-%m-%d %H:%M:%S'),
                    time_zone=time_zone,
                    candidate_limit=candidate_limit,
                    target_limit=target_limit,
                    weather_provider=weather_provider,
                    max_locations=max_locations,
                    min_height_diff=min_height_diff,
                    road_radius_km=road_radius_km,
                    network_type=network_type,
                    observation_style=style.value,
                    avoid_popular_spots=avoid_popular_spots,
                    prefer_quiet_at_night=prefer_quiet_at_night,
                    popularity_radius_km=popularity_radius_km,
                    db_config_path=db_config_path,
                )
            except MCPError as exc:
                night_results.append(
                    NightlyStargazingPlan(
                        night_index=night_index,
                        date=local_date,
                        night_window=window,
                        error=f'{exc.code}: {exc.message}',
                        warnings=[f'night_plan_failed:{exc.code}'],
                    )
                )
                continue
            night_results.append(
                NightlyStargazingPlan(
                    night_index=night_index,
                    date=local_date,
                    night_window=window,
                    plan=plan,
                    warnings=plan.summary.warnings,
                )
            )
        successful = [night for night in night_results if night.plan and night.plan.candidates]
        best_night = (
            max(successful, key=lambda night: night.plan.candidates[0].recommendation_score)
            if successful
            else None
        )
        best_candidate = best_night.plan.candidates[0] if best_night and best_night.plan else None
        warnings = sorted({warning for night in night_results for warning in night.warnings})
        return MultiNightStargazingPlan(
            query=MultiNightPlanningQuery(
                south=south,
                west=west,
                north=north,
                east=east,
                start_date=start_date,
                nights=nights,
                time_zone=time_zone,
                observation_style=style,
            ),
            summary=MultiNightPlanningSummary(
                generated_at=self._dependencies.now().isoformat(),
                requested_nights=nights,
                successful_nights=len(successful),
                best_night_index=best_night.night_index if best_night else None,
                best_night_date=best_night.date if best_night else None,
                best_location_name=best_candidate.location.name if best_candidate else None,
                best_score=best_candidate.recommendation_score if best_candidate else None,
                warnings=warnings,
            ),
            nights=night_results,
        )

    async def _resolve_agent_location(
        self, request: AgentPlanningRequest
    ) -> ResolvedPlanningLocation:
        intent = request.location
        if intent.bounds is not None:
            bounds = intent.bounds
            _validate_bounds(bounds.south, bounds.west, bounds.north, bounds.east)
            center = GeoPoint(
                lat=(bounds.south + bounds.north) / 2.0,
                lon=(bounds.west + bounds.east) / 2.0,
            )
            return ResolvedPlanningLocation(
                input_mode='bounds',
                center=center,
                bounds=bounds,
                resolution_source='caller',
            )

        if intent.center is not None:
            bounds = _bounds_from_center(intent.center, intent.radius_km)
            return ResolvedPlanningLocation(
                input_mode='center',
                center=intent.center,
                bounds=bounds,
                radius_km=intent.radius_km,
                resolution_source='caller',
            )

        if self._dependencies.resolve_place is None:
            raise MCPError(
                MCPError.CONFIGURATION_ERROR,
                'Place-name resolution is not configured for the agent-native planner.',
            )
        place_name = intent.place_name or ''
        resolved = await self._dependencies.resolve_place(place_name)
        center = GeoPoint(lat=resolved.lat, lon=resolved.lon)
        bounds = _bounds_from_center(center, intent.radius_km)
        return ResolvedPlanningLocation(
            input_mode='place_name',
            input_text=place_name,
            display_name=resolved.name,
            center=center,
            bounds=bounds,
            radius_km=intent.radius_km,
            resolution_source='server_geocoding_policy',
        )

    async def build_agent_plan(self, request: AgentPlanningRequest) -> AgentPlanningResult:
        """Build the agent-native planning contract.

        Provider selection and storage configuration remain server policy. The
        normalized request and every default are echoed in the result so an
        unfamiliar caller can audit what the service actually used.
        """

        resolved_location = await self._resolve_agent_location(request)
        equipment = _resolve_equipment(request)
        bounds = resolved_location.bounds
        plan = await self.build_multiday_plan(
            south=bounds.south,
            west=bounds.west,
            north=bounds.north,
            east=bounds.east,
            start_date=request.start_date,
            time_zone=request.time_zone,
            nights=request.nights,
            candidate_limit=request.candidate_limit,
            target_limit=request.target_limit,
            weather_provider='all',
            max_locations=max(10, request.candidate_limit * 3),
            observation_style=request.observation_style.value,
            avoid_popular_spots=request.avoid_popular_spots,
            prefer_quiet_at_night=request.prefer_quiet_at_night,
            popularity_radius_km=request.popularity_radius_km,
            db_config_path=None,
        )

        choices: list[tuple[str, PlannedLocationCandidate, BestStargazingPlan]] = []
        for night in plan.nights:
            if night.plan is None:
                continue
            choices.extend(
                (night.date, candidate, night.plan) for candidate in night.plan.candidates
            )
        choices.sort(key=lambda item: item[1].recommendation_score, reverse=True)

        uncertainties: list[PlanningUncertainty] = []
        missing_inputs: list[PlanningMissingInput] = []
        would_change_if: list[PlanningChangeCondition] = []
        next_actions: list[PlanningNextAction] = []
        evidence: list[PlanningEvidence] = []
        retrieved_at = self._dependencies.now().isoformat()

        if not choices:
            uncertainties.append(
                PlanningUncertainty(
                    code='no_candidates',
                    level=UncertaintyLevel.HIGH,
                    message=(
                        'No usable observing candidates were returned for the requested period.'
                    ),
                    impact='A first-choice session cannot be selected.',
                )
            )
            next_actions.append(
                PlanningNextAction(
                    action='expand_search_area',
                    reason='A wider radius or exact bounds may produce viable candidates.',
                )
            )
            return AgentPlanningResult(
                request=request,
                resolved_location=resolved_location,
                evidence=evidence,
                uncertainties=uncertainties,
                missing_inputs=missing_inputs,
                would_change_if=would_change_if,
                next_actions=next_actions,
            )

        decision_date, selected, selected_plan = choices[0]
        if selected.score_breakdown is None:
            raise MCPError(
                MCPError.CONFIGURATION_ERROR,
                'Agent-native planning requires candidate score_breakdown data.',
            )
        decision_targets = selected.top_targets
        if equipment is not None and self._dependencies.fetch_equipment_targets is not None:
            try:
                matched = await self._dependencies.fetch_equipment_targets(
                    **equipment.model_dump(exclude={'preset'}),
                    lon=selected.location.lon,
                    lat=selected.location.lat,
                    time=selected_plan.query.time,
                    time_zone=request.time_zone,
                    limit=request.target_limit,
                )
                decision_targets = [
                    PlanningTarget(
                        name=item['name'],
                        category=item.get('type', 'deep_sky'),
                        score=item.get('suitability_score'),
                    )
                    for item in matched.get('targets', [])[: request.target_limit]
                ]
            except Exception as exc:
                uncertainties.append(
                    PlanningUncertainty(
                        code='equipment_target_matching_failed',
                        level=UncertaintyLevel.MEDIUM,
                        message=str(exc),
                        impact=(
                            'The location decision remains valid, but targets use '
                            'generic sky ranking.'
                        ),
                    )
                )

        selected_night = next(
            night
            for night in plan.nights
            if night.date == decision_date and night.plan is selected_plan
        )
        decision = AgentPlanningDecision(
            date=decision_date,
            location=selected.location,
            recommendation_score=selected.recommendation_score,
            score_breakdown=selected.score_breakdown,
            reason_summary=selected_plan.summary.recommended_location_reason_summary,
            observation_window=selected.best_observation_window,
            targets=decision_targets,
            equipment=equipment,
        )

        alternatives: list[AgentPlanningAlternative] = []
        for alternative_date, candidate, _night_plan in choices[1 : request.candidate_limit + 1]:
            if candidate.score_breakdown is None:
                continue
            alternatives.append(
                AgentPlanningAlternative(
                    date=alternative_date,
                    location=candidate.location,
                    recommendation_score=candidate.recommendation_score,
                    score_breakdown=candidate.score_breakdown,
                    score_difference=round(
                        max(0.0, selected.recommendation_score - candidate.recommendation_score), 2
                    ),
                    comparison=_score_comparison(
                        selected.score_breakdown, candidate.score_breakdown
                    ),
                )
            )

        evidence.append(
            PlanningEvidence(
                kind=EvidenceKind.PLACE,
                source='analysis_area',
                retrieved_at=retrieved_at,
                applies_to=decision_date,
                resource_id=selected_plan.query.analysis_resource_id,
                facts={
                    'name': selected.location.name,
                    'lat': selected.location.lat,
                    'lon': selected.location.lon,
                    'place_score': selected.score_breakdown.place_base_score,
                    'bortle_class': selected.location.bortle_class,
                },
            )
        )
        if selected.weather_summary is not None:
            evidence.append(
                PlanningEvidence(
                    kind=EvidenceKind.WEATHER,
                    source='server_weather_policy',
                    retrieved_at=retrieved_at,
                    applies_to=decision_date,
                    facts=selected.weather_summary.model_dump(),
                )
            )
        evidence.append(
            PlanningEvidence(
                kind=EvidenceKind.SKY,
                source='nightly_forecast',
                retrieved_at=retrieved_at,
                applies_to=decision_date,
                facts={
                    'moon_phase': selected.moon_phase,
                    'moon_illumination': selected.moon_illumination,
                    'night_window': (
                        selected_night.night_window.model_dump()
                        if selected_night.night_window is not None
                        else None
                    ),
                    'target_count': len(decision_targets),
                },
            )
        )
        if equipment is not None:
            evidence.append(
                PlanningEvidence(
                    kind=EvidenceKind.EQUIPMENT,
                    source='equipment_preset_and_overrides',
                    retrieved_at=retrieved_at,
                    applies_to=decision_date,
                    facts=equipment.model_dump(),
                )
            )

        for note in selected.notes:
            uncertainties.append(
                PlanningUncertainty(
                    code='partial_downstream_data',
                    level=UncertaintyLevel.MEDIUM,
                    message=note,
                    impact='The score may rely on fallback values or omit one evidence source.',
                )
            )
        if request.avoid_popular_spots or request.prefer_quiet_at_night:
            uncertainties.append(
                PlanningUncertainty(
                    code='popularity_is_heuristic',
                    level=UncertaintyLevel.LOW,
                    message=(
                        'Popularity and night-quiet signals are heuristic estimates, '
                        'not live counts.'
                    ),
                    impact='Actual crowd conditions can differ from the ranking adjustment.',
                )
            )
        if request.equipment is None and request.observation_style == ObservationStyle.DEEP_SKY:
            missing_inputs.append(
                PlanningMissingInput(
                    field='equipment',
                    reason='Optics materially affect which deep-sky targets fit the field of view.',
                )
            )

        would_change_if.append(
            PlanningChangeCondition(
                factor='weather',
                condition=(
                    'Cloud, precipitation, or wind forecasts change materially before departure.'
                ),
                expected_effect='The best night or location may be reranked.',
            )
        )
        if alternatives:
            would_change_if.append(
                PlanningChangeCondition(
                    factor='score_gap',
                    condition=(
                        'The leading factors shift by more than '
                        f'{alternatives[0].score_difference:.2f} '
                        'points.'
                    ),
                    expected_effect='The first alternative could overtake the current decision.',
                )
            )
        if request.equipment is None:
            would_change_if.append(
                PlanningChangeCondition(
                    factor='equipment',
                    condition='A telescope preset or custom optics are supplied.',
                    expected_effect='Target ordering and suitability scores may change.',
                )
            )

        next_actions.append(
            PlanningNextAction(
                action='recheck_weather',
                reason='Refresh the forecast near departure because weather is time-sensitive.',
            )
        )
        next_actions.append(
            PlanningNextAction(
                action='confirm_access',
                reason='Verify current road access, parking, and local observing restrictions.',
            )
        )
        if request.equipment is None:
            next_actions.append(
                PlanningNextAction(
                    action='provide_equipment',
                    reason=(
                        'A preset or optical configuration enables equipment-aware target matching.'
                    ),
                )
            )

        return AgentPlanningResult(
            request=request,
            resolved_location=resolved_location,
            decision=decision,
            alternatives=alternatives,
            evidence=evidence,
            uncertainties=uncertainties,
            missing_inputs=missing_inputs,
            would_change_if=would_change_if,
            next_actions=next_actions,
        )
