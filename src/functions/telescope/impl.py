import asyncio
from typing import Any

import astropy.units as u
from astropy.coordinates import EarthLocation
from astropy.time import Time
from stargazing_core import TelescopeConfig, match_telescope_targets

from src.logging_config import set_request_id
from src.response import MCPError, format_response
from src.server_instance import mcp
from src.utils import parse_observation_time


async def _respond_with_mcp_error(operation) -> dict[str, Any]:
    set_request_id()
    try:
        return await operation
    except MCPError as exc:
        return exc.to_response()


@mcp.tool()
async def get_telescope_targets(
    focal_length_mm: float,
    lon: float,
    lat: float,
    time: str,
    time_zone: str,
    aperture_mm: float | None = None,
    sensor_width_mm: float | None = None,
    sensor_height_mm: float | None = None,
    sensor_pixel_size_um: float | None = None,
    central_obstruction_pct: float = 0,
    reducer_factor: float = 1.0,
    barlow_factor: float = 1.0,
    mount_type: str = 'equatorial',
    filter_type: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Recommend astrophotography targets for a telescope setup.

    Given a telescope/camera configuration and observing location+time,
    returns a ranked list of deep-sky objects best suited for imaging.

    Args:
        focal_length_mm: Telescope focal length in mm (e.g. 250 for RedCat51)
        lon: Observer longitude in degrees
        lat: Observer latitude in degrees
        time: Observation time string "YYYY-MM-DD HH:MM:SS"
        time_zone: IANA timezone string (e.g. "Asia/Shanghai", "UTC")
        aperture_mm: Telescope aperture in mm (optional, for limiting magnitude)
        sensor_width_mm: Camera sensor width in mm (optional)
        sensor_height_mm: Camera sensor height in mm (optional)
        sensor_pixel_size_um: Camera pixel size in microns (optional)
        central_obstruction_pct: Central obstruction percentage (0-50)
        reducer_factor: Focal reducer factor (default 1.0)
        barlow_factor: Barlow/extender factor (default 1.0)
        mount_type: "equatorial" or "altaz" (default "equatorial")
        filter_type: Filter type — "Hα", "OIII", "SII", or None for LRGB
        limit: Maximum number of targets to return (default 20)

    Returns:
        Dict with "data" containing a sorted list of telescope targets.
        Each target includes suitability_score, fov_fit_score,
        surface_brightness, filter_match_score, and mosaic_recommended.
    """
    return await _respond_with_mcp_error(
        _get_telescope_targets(
            focal_length_mm,
            lon,
            lat,
            time,
            time_zone,
            aperture_mm,
            sensor_width_mm,
            sensor_height_mm,
            sensor_pixel_size_um,
            central_obstruction_pct,
            reducer_factor,
            barlow_factor,
            mount_type,
            filter_type,
            limit,
        )
    )


async def _get_telescope_targets(
    focal_length_mm: float,
    lon: float,
    lat: float,
    time: str,
    time_zone: str,
    aperture_mm: float | None,
    sensor_width_mm: float | None,
    sensor_height_mm: float | None,
    sensor_pixel_size_um: float | None,
    central_obstruction_pct: float,
    reducer_factor: float,
    barlow_factor: float,
    mount_type: str,
    filter_type: str | None,
    limit: int,
) -> dict[str, Any]:
    # Parse time
    dt = parse_observation_time(time, time_zone)

    # Build TelescopeConfig
    config = TelescopeConfig(
        focal_length_mm=focal_length_mm,
        aperture_mm=aperture_mm,
        sensor_width_mm=sensor_width_mm,
        sensor_height_mm=sensor_height_mm,
        sensor_pixel_size_um=sensor_pixel_size_um,
        central_obstruction_pct=central_obstruction_pct,
        reducer_factor=reducer_factor,
        barlow_factor=barlow_factor,
        mount_type=mount_type,
        filter_type=filter_type,
    )

    # Create observer location
    observer = EarthLocation(lat=lat * u.deg, lon=lon * u.deg)

    # Convert to astropy Time
    t = Time(dt)

    # Run matching in thread (astropy is blocking)
    results = await asyncio.to_thread(
        match_telescope_targets,
        config,
        observer,
        t,
        limit,
    )

    return format_response(
        {
            'targets': results['targets'],
            'moon': results['moon'],
            'config': config.model_dump(exclude_none=True),
            'total': len(results['targets']),
        }
    )


@mcp.tool()
async def get_shooting_plan(
    focal_length_mm: float,
    lon: float,
    lat: float,
    time: str,
    time_zone: str = 'UTC',
    aperture_mm: float | None = None,
    sensor_width_mm: float | None = None,
    sensor_height_mm: float | None = None,
    sensor_pixel_size_um: float | None = None,
    central_obstruction_pct: float = 0,
    reducer_factor: float = 1.0,
    barlow_factor: float = 1.0,
    mount_type: str = 'equatorial',
    filter_type: str | None = None,
    limit: int = 20,
    min_altitude: float = 25.0,
) -> dict:
    """Generate a single-night astrophotography shooting plan.

    Runs match_telescope_targets then generate_shooting_schedule,
    returning targets + moon + timed shooting slots in one response.
    """
    from datetime import datetime

    import pytz
    from stargazing_core._shooting_plan import generate_shooting_schedule

    config = TelescopeConfig(
        focal_length_mm=focal_length_mm,
        aperture_mm=aperture_mm,
        sensor_width_mm=sensor_width_mm,
        sensor_height_mm=sensor_height_mm,
        sensor_pixel_size_um=sensor_pixel_size_um,
        central_obstruction_pct=central_obstruction_pct,
        reducer_factor=reducer_factor,
        barlow_factor=barlow_factor,
        mount_type=mount_type,
        filter_type=filter_type,
    )

    observer = EarthLocation(lat=lat * u.deg, lon=lon * u.deg)

    tz = pytz.timezone(time_zone)
    dt = tz.localize(datetime.fromisoformat(time))
    t = Time(dt)

    results = await asyncio.to_thread(
        match_telescope_targets,
        config,
        observer,
        t,
        limit,
    )

    targets = results['targets']
    moon = results['moon']
    dusk = targets[0]['civil_dusk'] if targets else t.iso
    dawn = targets[0]['civil_dawn'] if targets else t.iso

    plan = generate_shooting_schedule(targets, moon, dusk, dawn, min_alt=min_altitude)

    return format_response(
        {
            'targets': targets,
            'moon': moon,
            'plan': plan.model_dump(),
            'config': config.model_dump(exclude_none=True),
            'total': len(targets),
        }
    )
