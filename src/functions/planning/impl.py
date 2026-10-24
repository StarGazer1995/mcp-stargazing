"""Thin MCP adapters for the planning application service."""

import asyncio
from datetime import UTC, datetime
from typing import Any

from src.celestial import calculate_civil_night_window
from src.functions.celestial.impl import build_nightly_forecast_capability
from src.functions.places.impl import analyze_area_capability
from src.functions.telescope.impl import build_telescope_targets_capability
from src.functions.weather.geocoding import resolve_place_name
from src.functions.weather.impl import fetch_weather_by_position_capability
from src.logging_config import set_request_id
from src.response import MCPError, format_response
from src.schemas.places import StargazingLocation
from src.schemas.planning import ObservationStyle, PlannedLocationCandidate
from src.server_instance import mcp
from src.services.planning import PlanningDependencies, PlanningService
from src.utils import create_earth_location


async def _search_places(**kwargs) -> dict[str, Any]:
    result = await analyze_area_capability(**kwargs)
    payload = result.result
    return payload.model_dump() if hasattr(payload, 'model_dump') else payload


async def _fetch_weather(**kwargs) -> dict[str, Any]:
    result = await asyncio.to_thread(fetch_weather_by_position_capability, **kwargs)
    return result.model_dump() if hasattr(result, 'model_dump') else result


async def _fetch_forecast(**kwargs) -> dict[str, Any]:
    result = await build_nightly_forecast_capability(**kwargs)
    return result.model_dump() if hasattr(result, 'model_dump') else result


async def _fetch_night_window(lat: float, lon: float, reference: datetime):
    return await asyncio.to_thread(
        calculate_civil_night_window,
        create_earth_location(lat, lon),
        reference,
    )


async def _resolve_place(place_name: str):
    return await asyncio.to_thread(resolve_place_name, place_name)


def _build_planning_service() -> PlanningService:
    """Bind production dependencies while keeping the service transport-free."""
    return PlanningService(
        PlanningDependencies(
            search_places=_search_places,
            fetch_weather=_fetch_weather,
            fetch_forecast=_fetch_forecast,
            fetch_night_window=_fetch_night_window,
            now=lambda: datetime.now(UTC),
            resolve_place=_resolve_place,
            fetch_equipment_targets=build_telescope_targets_capability,
        )
    )


async def _respond_with_mcp_error(operation) -> dict[str, Any]:
    """Wrap service models and structured errors in the public MCP envelope."""
    set_request_id()
    try:
        result = await operation
        return format_response(result.model_dump())
    except MCPError as exc:
        return exc.to_response()


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
    """Compatibility shim for existing internal callers and focused tests."""
    return await _build_planning_service().evaluate_candidate(
        location=location,
        time=time,
        time_zone=time_zone,
        target_limit=target_limit,
        weather_provider=weather_provider,
        observation_style=observation_style,
        avoid_popular_spots=avoid_popular_spots,
        prefer_quiet_at_night=prefer_quiet_at_night,
        popularity_radius_km=popularity_radius_km,
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

    This is a stable MCP adapter. Validation, orchestration, ranking, and
    explanation live in :class:`src.services.planning.PlanningService`.
    """
    service = _build_planning_service()
    return await _respond_with_mcp_error(
        service.build_best_plan(
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
            observation_style=observation_style,
            avoid_popular_spots=avoid_popular_spots,
            prefer_quiet_at_night=prefer_quiet_at_night,
            popularity_radius_km=popularity_radius_km,
            db_config_path=db_config_path,
        )
    )


@mcp.tool()
async def get_multiday_stargazing_plan(
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
    db_config_path: str = None,
) -> dict[str, Any]:
    """Compare one to seven consecutive nights and recommend the best night and place.

    Each night uses its own civil-dark window. The application service reuses
    single-night planning directly, without chaining through another MCP tool.
    """
    service = _build_planning_service()
    return await _respond_with_mcp_error(
        service.build_multiday_plan(
            south=south,
            west=west,
            north=north,
            east=east,
            start_date=start_date,
            time_zone=time_zone,
            nights=nights,
            candidate_limit=candidate_limit,
            target_limit=target_limit,
            weather_provider=weather_provider,
            max_locations=max_locations,
            min_height_diff=min_height_diff,
            road_radius_km=road_radius_km,
            network_type=network_type,
            observation_style=observation_style,
            avoid_popular_spots=avoid_popular_spots,
            prefer_quiet_at_night=prefer_quiet_at_night,
            popularity_radius_km=popularity_radius_km,
            db_config_path=db_config_path,
        )
    )
