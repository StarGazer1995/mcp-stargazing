import asyncio
from typing import Any

from src.celestial import (
    calculate_moon_info,
    calculate_nightly_forecast,
    celestial_pos,
    celestial_rise_set,
    get_constellation_center,
)
from src.logging_config import set_request_id
from src.response import MCPError, format_response
from src.schemas import (
    CelestialPosition,
    ConstellationInfo,
    MoonInfo,
    NightlyForecast,
    RiseSet,
    VisiblePlanet,
)
from src.server_instance import mcp
from src.utils import parse_observation_time, process_location_and_time


async def _respond_with_mcp_error(operation) -> dict[str, Any]:
    """Convert domain validation errors into the standard MCP response shape."""
    set_request_id()
    try:
        return await operation
    except MCPError as exc:
        return exc.to_response()


@mcp.tool()
async def get_celestial_pos(
    celestial_object: str, lon: float, lat: float, time: str, time_zone: str
) -> dict[str, Any]:
    """Calculate the altitude and azimuth angles of a celestial object.

    Args:
        celestial_object: Name of object (e.g. "sun", "moon", "andromeda")
        lon: Observer longitude in degrees
        lat: Observer latitude in degrees
        time: Observation time string "YYYY-MM-DD HH:MM:SS"
        time_zone: IANA timezone string

    Returns:
        Dict with keys "data", "_meta". "data" contains "altitude" and "azimuth" (degrees).
    """

    async def operation() -> dict[str, Any]:
        location, time_info = process_location_and_time(lon, lat, time, time_zone)
        # Run synchronous celestial calculations in a thread to avoid blocking the event loop.
        alt, az = await asyncio.to_thread(celestial_pos, celestial_object, location, time_info)
        pos = CelestialPosition(altitude=alt, azimuth=az)
        return format_response(pos.model_dump())

    return await _respond_with_mcp_error(operation())


@mcp.tool()
async def get_celestial_rise_set(
    celestial_object: str, lon: float, lat: float, time: str, time_zone: str
) -> dict[str, Any]:
    """Calculate the rise and set times of a celestial object.

    Args:
        celestial_object: Name of object (e.g. "sun", "moon", "andromeda")
        lon: Observer longitude in degrees
        lat: Observer latitude in degrees
        time: Date string "YYYY-MM-DD HH:MM:SS"
        time_zone: IANA timezone string

    Returns:
        Dict with keys "data", "_meta". "data" contains "rise_time" and "set_time".
    """

    async def operation() -> dict[str, Any]:
        location, time_info = process_location_and_time(lon, lat, time, time_zone)
        # Run synchronous celestial calculations in a separate thread
        rise_time, set_time = await asyncio.to_thread(
            celestial_rise_set, celestial_object, location, time_info
        )
        rise_set = RiseSet(
            rise_time=rise_time.isoformat() if rise_time else None,
            set_time=set_time.isoformat() if set_time else None,
        )
        return format_response(rise_set.model_dump())

    return await _respond_with_mcp_error(operation())


@mcp.tool()
async def get_moon_info(time: str, time_zone: str) -> dict[str, Any]:
    """Get detailed information about the Moon's phase and position.

    Args:
        time: Date string "YYYY-MM-DD HH:MM:SS"
        time_zone: IANA timezone string

    Returns:
        Dict with keys "data", "_meta". "data" contains illumination, phase_name, age_days, etc.
    """

    async def operation() -> dict[str, Any]:
        dt = parse_observation_time(time, time_zone)
        result = await asyncio.to_thread(calculate_moon_info, dt)
        moon_info = MoonInfo(**result)
        return format_response(moon_info.model_dump())

    return await _respond_with_mcp_error(operation())


@mcp.tool()
async def list_visible_planets(lon: float, lat: float, time: str, time_zone: str) -> dict[str, Any]:
    """Get a list of solar system planets currently visible (above horizon).

    Args:
        lon: Observer longitude in degrees
        lat: Observer latitude in degrees
        time: Observation time string "YYYY-MM-DD HH:MM:SS"
        time_zone: IANA timezone string

    Returns:
        Dict with keys "data", "_meta". "data" is a list of planet dicts (name, altitude, azimuth).
    """

    async def operation() -> dict[str, Any]:
        location, time_info = process_location_and_time(lon, lat, time, time_zone)
        # Local import with alias avoids shadowing the module-level
        # `get_visible_planets = list_visible_planets` backward-compat alias (line below).
        from src.celestial import get_visible_planets as calc_visible_planets

        planets = await asyncio.to_thread(calc_visible_planets, location, time_info)
        models = [VisiblePlanet(**p) for p in planets]
        return format_response([m.model_dump() for m in models])

    return await _respond_with_mcp_error(operation())


# Backwards-compatible alias: export the original name pointing to the decorated wrapper
get_visible_planets = list_visible_planets


@mcp.tool()
async def get_constellation(
    constellation_name: str, lon: float, lat: float, time: str, time_zone: str
) -> dict[str, Any]:
    """Get the position (altitude/azimuth) of the center of a constellation.

    Args:
        constellation_name: Name of constellation (e.g. "Orion", "Ursa Major")
        lon: Observer longitude in degrees
        lat: Observer latitude in degrees
        time: Observation time string "YYYY-MM-DD HH:MM:SS"
        time_zone: IANA timezone string

    Returns:
        Dict with keys "data", "_meta". "data" contains name, altitude, azimuth.
    """

    async def operation() -> dict[str, Any]:
        location, time_info = process_location_and_time(lon, lat, time, time_zone)
        result = await asyncio.to_thread(
            get_constellation_center, constellation_name, location, time_info
        )
        const = ConstellationInfo(**result)
        return format_response(const.model_dump())

    return await _respond_with_mcp_error(operation())


@mcp.tool()
async def get_nightly_forecast(
    lon: float, lat: float, time: str, time_zone: str, limit: int = 20
) -> dict[str, Any]:
    """Get a curated list of best objects to view for the night.

    Args:
        lon: Observer longitude in degrees
        lat: Observer latitude in degrees
        time: Date string "YYYY-MM-DD HH:MM:SS" (Time of observation, or just date)
        time_zone: IANA timezone string
        limit: Max number of deep-sky objects to return (default 20)

    Returns:
        Dict with keys:
        - moon_phase: Moon details
        - planets: List of visible planets
        - deep_sky: Sorted list of deep sky objects (Messier/NGC)
    """

    async def operation() -> dict[str, Any]:
        location, time_info = process_location_and_time(lon, lat, time, time_zone)

        # Run in thread
        result = await asyncio.to_thread(calculate_nightly_forecast, location, time_info, limit)

        from src.schemas.celestial import DeepSkyObject

        forecast = NightlyForecast(
            moon_phase=MoonInfo(**result['moon_phase']),
            planets=[VisiblePlanet(**p) for p in result['planets']],
            deep_sky=[DeepSkyObject(**o) for o in result['deep_sky']],
        )
        return format_response(forecast.model_dump())

    return await _respond_with_mcp_error(operation())
