from typing import Dict, Optional, Any
import asyncio
from datetime import datetime
import pytz
from src.server_instance import mcp
from src.celestial import celestial_pos, celestial_rise_set, calculate_moon_info, get_visible_planets, get_constellation_center, calculate_nightly_forecast
from src.utils import process_location_and_time

from src.response import format_response

@mcp.tool()
async def get_celestial_pos(
    celestial_object: str,
    lon: float,
    lat: float,
    time: str,
    time_zone: str
) -> Dict[str, Any]:
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
    location, time_info = process_location_and_time(lon, lat, time, time_zone)
    # Run synchronous celestial calculations in a separate thread to avoid blocking the event loop
    alt, az = await asyncio.to_thread(celestial_pos, celestial_object, location, time_info)
    return format_response({
        "altitude": alt,
        "azimuth": az
    })

@mcp.tool()
async def get_celestial_rise_set(
    celestial_object: str,
    lon: float,
    lat: float,
    time: str,
    time_zone: str
) -> Dict[str, Any]:
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
    location, time_info = process_location_and_time(lon, lat, time, time_zone)
    # Run synchronous celestial calculations in a separate thread
    rise_time, set_time = await asyncio.to_thread(celestial_rise_set, celestial_object, location, time_info)
    return format_response({
        "rise_time": rise_time.isoformat() if rise_time else None,
        "set_time": set_time.isoformat() if set_time else None
    })

@mcp.tool()
async def get_moon_info(
    time: str,
    time_zone: str
) -> Dict[str, Any]:
    """Get detailed information about the Moon's phase and position.
    
    Args:
        time: Date string "YYYY-MM-DD HH:MM:SS"
        time_zone: IANA timezone string
        
    Returns:
        Dict with keys "data", "_meta". "data" contains illumination, phase_name, age_days, etc.
    """
    try:
        # Try standard format first
        dt = datetime.strptime(time, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            # Try ISO format
            dt = datetime.fromisoformat(time)
        except ValueError:
             raise ValueError(f"Time string '{time}' matches neither '%Y-%m-%d %H:%M:%S' nor ISO format.")

    if dt.tzinfo is None:
        tz = pytz.timezone(time_zone)
        dt = tz.localize(dt)
        
    result = await asyncio.to_thread(calculate_moon_info, dt)
    return format_response(result)

@mcp.tool()
async def get_visible_planets(
    lon: float,
    lat: float,
    time: str,
    time_zone: str
) -> Dict[str, Any]:
    """Get a list of solar system planets currently visible (above horizon).
    
    Args:
        lon: Observer longitude in degrees
        lat: Observer latitude in degrees
        time: Observation time string "YYYY-MM-DD HH:MM:SS"
        time_zone: IANA timezone string
        
    Returns:
        Dict with keys "data", "_meta". "data" is a list of planet dicts (name, altitude, azimuth).
    """
    location, time_info = process_location_and_time(lon, lat, time, time_zone)
    # Note: Function name collision with imported function 'get_visible_planets'
    # Use the imported function from src.celestial
    from src.celestial import get_visible_planets as calc_visible_planets
    planets = await asyncio.to_thread(calc_visible_planets, location, time_info)
    return format_response(planets)

@mcp.tool()
async def get_constellation(
    constellation_name: str,
    lon: float,
    lat: float,
    time: str,
    time_zone: str
) -> Dict[str, Any]:
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
    location, time_info = process_location_and_time(lon, lat, time, time_zone)
    result = await asyncio.to_thread(get_constellation_center, constellation_name, location, time_info)
    return format_response(result)

@mcp.tool()
async def get_nightly_forecast(
    lon: float,
    lat: float,
    time: str,
    time_zone: str,
    limit: int = 20
) -> Dict[str, Any]:
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
    location, time_info = process_location_and_time(lon, lat, time, time_zone)
    
    # Run in thread
    result = await asyncio.to_thread(calculate_nightly_forecast, location, time_info, limit)
    
    return format_response(result)
