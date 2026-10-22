import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from src.functions.celestial.impl import get_nightly_forecast
from src.functions.places.impl import analysis_area
from src.functions.weather.impl import get_weather_by_position
from src.logging_config import set_request_id
from src.response import MCPError, format_response
from src.schemas.places import StargazingLocation
from src.schemas.planning import (
    BestStargazingPlan,
    ObservationStyle,
    ObservationWindow,
    PlannedLocationCandidate,
    PlanningQuery,
    PlanningSummary,
    PlanningTarget,
    RecommendationDriver,
    WeatherPlanningSummary,
)
from src.server_instance import mcp
from src.utils import (
    ensure_timezone,
    parse_observation_time,
    parse_time_string,
    validate_coordinates,
)

# ── Cross-tool contract ─────────────────────────────────────────────────
# Planning calls other MCP tools via their ``.fn`` attribute (the raw
# function before FastMCP decorator wrapping).  This is the standard
# FastMCP chaining pattern.  Signature contracts are documented inline
# at each call site below; if an upstream tool changes its signature a
# test in ``test_mcp_tools.py`` will catch the mismatch.


@dataclass(frozen=True)
class _ObservationStyleProfile:
    """Weights and explanation used by one observer-goal profile."""

    place_weight: float
    weather_weight: float
    moon_penalty_multiplier: float
    reason: str | None


_STYLE_PROFILES = {
    ObservationStyle.BALANCED: _ObservationStyleProfile(0.65, 0.35, 1.0, None),
    ObservationStyle.DEEP_SKY: _ObservationStyleProfile(
        0.72,
        0.28,
        1.15,
        '深空摄影偏好提高了暗空与低月光条件的权重。',
    ),
    ObservationStyle.VISUAL: _ObservationStyleProfile(
        0.55,
        0.45,
        0.45,
        '目视观测偏好提高了实时天气权重并降低月光影响。',
    ),
    ObservationStyle.PLANETARY: _ObservationStyleProfile(
        0.42,
        0.58,
        0.08,
        '行星观测偏好显著降低月光惩罚并优先安排行星目标。',
    ),
    ObservationStyle.BEGINNER: _ObservationStyleProfile(
        0.60,
        0.40,
        0.25,
        '入门观测偏好兼顾天气、地点评分与交通便利性。',
    ),
}


def _validate_observation_style(value: str) -> ObservationStyle:
    """Normalize an observer-style string or raise a structured configuration error."""
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
    """Validate that the requested bounding box is geographically valid."""
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
    """Validate that a configuration integer is strictly positive."""
    if value < 1:
        raise MCPError(
            MCPError.CONFIGURATION_ERROR,
            f'{name} must be greater than or equal to 1.',
            {name: value},
        )


async def _respond_with_mcp_error(operation) -> dict[str, Any]:
    """Convert MCPError exceptions into the standard structured payload."""
    set_request_id()
    try:
        return await operation
    except MCPError as exc:
        return exc.to_response()


def _extract_required_data(result: dict[str, Any]) -> dict[str, Any]:
    """Extract data from a wrapped tool response or raise its structured error."""
    if result.get('_meta', {}).get('status') == 'error':
        error = result['error']
        raise MCPError(error['code'], error['message'], error.get('details'))
    return result['data']


def _extract_optional_data(result: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    """Extract data from a wrapped tool response and keep soft failures as notes."""
    if result.get('_meta', {}).get('status') == 'error':
        error = result['error']
        return None, f'{error["code"]}: {error["message"]}'
    return result['data'], None


def _parse_forecast_time(value: str, time_zone: str):
    """Parse a weather-forecast timestamp into a timezone-aware datetime."""
    return ensure_timezone(parse_time_string(value), time_zone)


def _pick_best_observation_window(
    hourly_items: list[dict[str, Any]], requested_time: str, time_zone: str
) -> ObservationWindow | None:
    """Pick the most promising hourly observation slot from the near-term forecast."""
    if not hourly_items:
        return None

    requested_dt = parse_observation_time(requested_time, time_zone)
    cutoff_dt = requested_dt + timedelta(hours=12)
    best_item = None
    best_score = None

    for item in hourly_items:
        time_value = item.get('time')
        if not time_value:
            continue
        forecast_dt = _parse_forecast_time(time_value, time_zone)
        if forecast_dt < requested_dt or forecast_dt > cutoff_dt:
            continue

        cloud_cover = item.get('cloud_cover_percent')
        precipitation = item.get('precipitation_probability')
        wind_speed = item.get('wind_speed_kph')

        score = 100.0
        if cloud_cover is not None:
            score -= float(cloud_cover) * 0.7
        if precipitation is not None:
            score -= float(precipitation) * 20.0
        if wind_speed is not None and float(wind_speed) > 20.0:
            score -= (float(wind_speed) - 20.0) * 1.5

        if best_score is None or score > best_score:
            best_item = item
            best_score = score

    if best_item is None:
        return None

    return ObservationWindow(
        start_time=best_item.get('time'),
        cloud_cover_percent=best_item.get('cloud_cover_percent'),
        precipitation_probability=best_item.get('precipitation_probability'),
        wind_speed_kph=best_item.get('wind_speed_kph'),
        weather_text=best_item.get('weather_text'),
    )


def _build_weather_summary(weather_data: dict[str, Any] | None) -> WeatherPlanningSummary | None:
    """Condense aggregated weather into a small planning-oriented summary."""
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
    """Convert nightly forecast output into a compact target list."""
    if forecast_data is None:
        return []

    targets: list[PlanningTarget] = []
    deep_sky = forecast_data.get('deep_sky', [])
    planets = forecast_data.get('planets', [])
    sources = (
        (planets, 'planet'),
        (deep_sky, 'deep_sky'),
    )
    if observation_style in {
        ObservationStyle.BALANCED,
        ObservationStyle.DEEP_SKY,
    }:
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
                )
            )

    return targets


def _compute_recommendation_score(
    location: StargazingLocation,
    weather_summary: WeatherPlanningSummary | None,
    best_window: ObservationWindow | None,
    moon_illumination: float | None,
    observation_style: ObservationStyle = ObservationStyle.BALANCED,
    popularity_adjustment: float = 0.0,
) -> float:
    """Combine place quality, weather, and moonlight into a simple planning score."""
    profile = _STYLE_PROFILES[observation_style]
    location_score = float(location.score or 0.0)
    weather_score = 55.0

    if weather_summary is not None:
        cloud_cover = weather_summary.cloud_cover_percent
        visibility = weather_summary.visibility_km
        wind_speed = weather_summary.wind_speed_kph

        if cloud_cover is not None:
            weather_score = max(0.0, 100.0 - float(cloud_cover))
        if visibility is not None:
            weather_score += min(20.0, float(visibility) * 1.5)
        if wind_speed is not None and float(wind_speed) > 20.0:
            weather_score -= min(20.0, (float(wind_speed) - 20.0) * 1.2)

    if best_window is not None and best_window.precipitation_probability is not None:
        weather_score -= float(best_window.precipitation_probability) * 20.0

    if moon_illumination is not None and moon_illumination > 0.7:
        weather_score -= (moon_illumination - 0.7) * 25.0 * profile.moon_penalty_multiplier

    combined = (
        location_score * profile.place_weight
        + max(0.0, weather_score) * profile.weather_weight
        + popularity_adjustment
    )
    if observation_style == ObservationStyle.BEGINNER and location.road_distance_km is not None:
        if location.road_distance_km <= 5.0:
            combined += 3.0
        elif location.road_distance_km > 20.0:
            combined -= 3.0
    return round(max(0.0, min(100.0, combined)), 2)


def _compute_popularity_preference_adjustment(
    location: StargazingLocation,
    avoid_popular_spots: bool,
    prefer_quiet_at_night: bool,
    popularity_radius_km: float,
) -> tuple[float, list[str]]:
    """Translate popularity preferences into planning-score adjustments and reasons."""
    if not avoid_popular_spots and not prefer_quiet_at_night:
        return 0.0, []

    radius_factor = max(0.5, min(1.5, popularity_radius_km / 3.0))
    adjustment = 0.0
    reasons: list[str] = []

    if avoid_popular_spots and location.static_popularity_risk_score is not None:
        risk_score = float(location.static_popularity_risk_score)
        risk_delta = (50.0 - risk_score) / 50.0
        adjustment += risk_delta * 7.0 * radius_factor
        if risk_score <= 35.0:
            reasons.append(f'静态热门风险约 {risk_score:.0f}/100，更符合避开热门点偏好。')
        elif risk_score >= 65.0:
            reasons.append(f'静态热门风险约 {risk_score:.0f}/100，已按偏好下调优先级。')

    if prefer_quiet_at_night and location.night_quiet_likelihood_score is not None:
        quiet_score = float(location.night_quiet_likelihood_score)
        confidence = float(location.temporal_popularity_confidence or 50.0)
        confidence_factor = max(0.35, min(1.0, confidence / 100.0))
        quiet_delta = (quiet_score - 50.0) / 50.0
        adjustment += quiet_delta * 7.0 * confidence_factor * radius_factor
        if quiet_score >= 65.0:
            reasons.append(
                f'夜间安静概率约 {quiet_score:.0f}/100'
                f'（置信度 {confidence:.0f}/100），更贴合夜间安静偏好。'
            )
        elif quiet_score <= 35.0:
            reasons.append(f'夜间持续活跃概率偏高，夜间安静概率仅约 {quiet_score:.0f}/100。')

    if (
        location.popularity_notes
        and (avoid_popular_spots or prefer_quiet_at_night)
        and len(reasons) < 2
    ):
        reasons.append(location.popularity_notes)

    return round(adjustment, 2), reasons[:2]


def _build_recommendation_reasons(
    location: StargazingLocation,
    weather_summary: WeatherPlanningSummary | None,
    best_window: ObservationWindow | None,
    moon_illumination: float | None,
    top_targets: list[PlanningTarget],
    observation_style: ObservationStyle = ObservationStyle.BALANCED,
    popularity_reasons: list[str] | None = None,
) -> list[str]:
    """Create short human-readable explanations for a recommendation."""
    reasons: list[str] = []

    if location.bortle_class is not None:
        reasons.append(f'波特尔等级约为 {location.bortle_class}，暗空条件较清晰。')
    elif location.score is not None:
        reasons.append(f'地点基础观星评分为 {location.score:.1f}。')
    style_reason = _STYLE_PROFILES[observation_style].reason
    if style_reason:
        reasons.append(style_reason)
    if popularity_reasons:
        reasons.extend(popularity_reasons)

    if weather_summary is not None and weather_summary.cloud_cover_percent is not None:
        reasons.append(f'当前云量约 {weather_summary.cloud_cover_percent:.0f}%。')
    if weather_summary is not None and weather_summary.visibility_km is not None:
        reasons.append(f'当前能见度约 {weather_summary.visibility_km:.1f} km。')
    if best_window is not None and best_window.start_time is not None:
        reasons.append(f'建议优先在 {best_window.start_time} 附近观测。')
    if moon_illumination is not None:
        reasons.append(f'月面照明比例约为 {moon_illumination:.0%}。')
    if top_targets:
        target_names = ', '.join(target.name for target in top_targets[:3])
        reasons.append(f'优先目标包括 {target_names}。')

    return reasons[:5]


def _derive_primary_recommendation_drivers(
    candidate: PlannedLocationCandidate | None,
    avoid_popular_spots: bool,
    prefer_quiet_at_night: bool,
    observation_style: ObservationStyle = ObservationStyle.BALANCED,
) -> list[RecommendationDriver]:
    """Summarize the main structured drivers behind the top recommendation."""
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
        cloud_cover = weather_summary.cloud_cover_percent
        visibility = weather_summary.visibility_km
        if cloud_cover is not None and float(cloud_cover) <= 25.0:
            drivers.append(RecommendationDriver.CLEAR_WEATHER)
        elif visibility is not None and float(visibility) >= 15.0:
            drivers.append(RecommendationDriver.GOOD_VISIBILITY)

    if observation_style != ObservationStyle.BALANCED:
        drivers.append(RecommendationDriver.OBSERVATION_STYLE_FIT)

    if (
        avoid_popular_spots
        and location.static_popularity_risk_score is not None
        and float(location.static_popularity_risk_score) <= 35.0
    ):
        drivers.append(RecommendationDriver.LOW_POPULARITY_RISK)

    if (
        prefer_quiet_at_night
        and location.night_quiet_likelihood_score is not None
        and float(location.night_quiet_likelihood_score) >= 65.0
    ):
        drivers.append(RecommendationDriver.QUIET_AT_NIGHT)

    if candidate.top_targets:
        drivers.append(RecommendationDriver.STRONG_TARGETS)

    return drivers[:4]


def _build_recommended_location_reason_summary(
    candidate: PlannedLocationCandidate | None,
    primary_drivers: list[RecommendationDriver],
) -> str | None:
    """Convert the top candidate's main drivers into a concise Chinese summary."""
    if candidate is None:
        return None

    label_map = {
        RecommendationDriver.DARK_SKY: '暗空条件更好',
        RecommendationDriver.HIGH_PLACE_SCORE: '地点基础评分更高',
        RecommendationDriver.CLEAR_WEATHER: '天气更晴朗',
        RecommendationDriver.GOOD_VISIBILITY: '能见度更好',
        RecommendationDriver.OBSERVATION_STYLE_FIT: '观测目标偏好匹配',
        RecommendationDriver.LOW_POPULARITY_RISK: '热门度风险更低',
        RecommendationDriver.QUIET_AT_NIGHT: '夜间更安静',
        RecommendationDriver.STRONG_TARGETS: '可观测目标更强',
    }
    labels = [label_map[driver] for driver in primary_drivers]
    if labels:
        joined = '、'.join(labels[:3])
        return f'{candidate.location.name} 当前主要因{joined}而成为首选。'

    if candidate.recommendation_reasons:
        return candidate.recommendation_reasons[0]

    return None


async def _evaluate_candidate(
    location: StargazingLocation,
    time: str,
    time_zone: str,
    target_limit: int,
    weather_provider: str,
    observation_style: ObservationStyle = ObservationStyle.BALANCED,
    avoid_popular_spots: bool = False,
    prefer_quiet_at_night: bool = False,
    popularity_radius_km: float = 3.0,
) -> PlannedLocationCandidate:
    """Evaluate one candidate place by attaching weather and target summaries."""
    weather_result, forecast_result = await asyncio.gather(
        asyncio.to_thread(
            get_weather_by_position.fn,
            lat=location.lat,
            lon=location.lon,
            provider=weather_provider,
        ),
        get_nightly_forecast.fn(
            lon=location.lon, lat=location.lat, time=time, time_zone=time_zone, limit=target_limit
        ),
    )

    notes: list[str] = []
    weather_data, weather_note = _extract_optional_data(weather_result)
    forecast_data, forecast_note = _extract_optional_data(forecast_result)
    if weather_note is not None:
        notes.append(f'天气摘要降级处理：{weather_note}')
    if forecast_note is not None:
        notes.append(f'夜间目标降级处理：{forecast_note}')

    weather_summary = _build_weather_summary(weather_data)
    best_window = None
    if weather_data is not None:
        hourly_items = weather_data.get('summary', {}).get('hourly', [])
        best_window = _pick_best_observation_window(hourly_items, time, time_zone)

    top_targets = _build_top_targets(forecast_data, target_limit, observation_style)
    moon_phase = None
    moon_illumination = None
    if forecast_data is not None:
        moon_phase = forecast_data.get('moon_phase', {}).get('phase_name')
        moon_illumination = forecast_data.get('moon_phase', {}).get('illumination')

    popularity_adjustment, popularity_reasons = _compute_popularity_preference_adjustment(
        location,
        avoid_popular_spots=avoid_popular_spots,
        prefer_quiet_at_night=prefer_quiet_at_night,
        popularity_radius_km=popularity_radius_km,
    )
    recommendation_score = _compute_recommendation_score(
        location,
        weather_summary,
        best_window,
        moon_illumination,
        observation_style=observation_style,
        popularity_adjustment=popularity_adjustment,
    )
    recommendation_reasons = _build_recommendation_reasons(
        location,
        weather_summary,
        best_window,
        moon_illumination,
        top_targets,
        observation_style=observation_style,
        popularity_reasons=popularity_reasons,
    )

    return PlannedLocationCandidate(
        rank=1,
        recommendation_score=recommendation_score,
        recommendation_reasons=recommendation_reasons,
        location=location,
        weather_summary=weather_summary,
        best_observation_window=best_window,
        moon_phase=moon_phase,
        moon_illumination=moon_illumination,
        top_targets=top_targets,
        notes=notes,
    )


@mcp.tool()
async def get_best_stargazing_plan(
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
    db_config_path: str = None,
) -> dict[str, Any]:
    """Create a composite stargazing plan for a region and time.

    This planning tool combines:
    - candidate place search from ``analysis_area``
    - weather summaries from ``get_weather_by_position``
    - astronomy targets from ``get_nightly_forecast``

    Args:
        south, west, north, east: Bounding box coordinates.
        time: Observation time string in ISO format or ``YYYY-MM-DD HH:MM:SS``.
        time_zone: IANA timezone string.
        candidate_limit: Maximum number of candidate places to evaluate.
        target_limit: Maximum number of recommended targets per place.
        weather_provider: Weather provider mode passed to weather tools.
        max_locations: Maximum number of area-analysis candidates to search.
        min_height_diff: Minimum elevation difference for prominence.
        road_radius_km: Search radius for road access.
        network_type: Type of road network to analyze.
        observation_style: Observer-goal profile. Supported values are balanced,
            deep_sky, visual, planetary, and beginner.
        avoid_popular_spots: Penalize heuristically popular locations during place ranking.
        prefer_quiet_at_night: Favor places that are likelier to quiet down at night.
        popularity_radius_km: Preference horizon for popularity heuristics.
        db_config_path: Optional path to database config.

    Returns:
        Dict with keys ``data`` and ``_meta``. ``data`` contains the normalized
        query, a plan summary, and ranked candidate recommendations.
    """

    async def operation() -> dict[str, Any]:
        _validate_bounds(south, west, north, east)
        _validate_positive_int('candidate_limit', candidate_limit)
        _validate_positive_int('target_limit', target_limit)
        _validate_positive_int('max_locations', max_locations)
        normalized_style = _validate_observation_style(observation_style)
        if popularity_radius_km <= 0:
            raise MCPError(
                MCPError.CONFIGURATION_ERROR,
                'popularity_radius_km must be greater than 0.',
                {'popularity_radius_km': popularity_radius_km},
            )
        parse_observation_time(time, time_zone)

        places_result = await analysis_area.fn(
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
        places_data = _extract_required_data(places_result)
        place_items = [
            StargazingLocation(**item) for item in places_data.get('items', [])[:candidate_limit]
        ]

        ranked_candidates = await asyncio.gather(
            *[
                _evaluate_candidate(
                    location=item,
                    time=time,
                    time_zone=time_zone,
                    target_limit=target_limit,
                    weather_provider=weather_provider,
                    observation_style=normalized_style,
                    avoid_popular_spots=avoid_popular_spots,
                    prefer_quiet_at_night=prefer_quiet_at_night,
                    popularity_radius_km=popularity_radius_km,
                )
                for item in place_items
            ]
        )
        ranked_candidates = sorted(
            ranked_candidates, key=lambda candidate: candidate.recommendation_score, reverse=True
        )

        warnings = sorted({note for candidate in ranked_candidates for note in candidate.notes})

        for index, candidate in enumerate(ranked_candidates, start=1):
            candidate.rank = index

        top_candidate = ranked_candidates[0] if ranked_candidates else None
        primary_drivers = _derive_primary_recommendation_drivers(
            top_candidate,
            avoid_popular_spots=avoid_popular_spots,
            prefer_quiet_at_night=prefer_quiet_at_night,
            observation_style=normalized_style,
        )
        reason_summary = _build_recommended_location_reason_summary(top_candidate, primary_drivers)

        plan = BestStargazingPlan(
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
                observation_style=normalized_style,
                avoid_popular_spots=avoid_popular_spots,
                prefer_quiet_at_night=prefer_quiet_at_night,
                popularity_radius_km=popularity_radius_km,
                analysis_resource_id=places_data.get('resource_id'),
            ),
            summary=PlanningSummary(
                generated_at=datetime.now(UTC).isoformat(),
                requested_time=time,
                time_zone=time_zone,
                total_candidates=len(ranked_candidates),
                recommended_location_name=(
                    ranked_candidates[0].location.name if ranked_candidates else None
                ),
                popularity_preferences_enabled=avoid_popular_spots or prefer_quiet_at_night,
                primary_recommendation_drivers=primary_drivers,
                recommended_location_reason_summary=reason_summary,
                warnings=warnings,
            ),
            candidates=ranked_candidates,
        )
        return format_response(plan.model_dump())

    return await _respond_with_mcp_error(operation())
