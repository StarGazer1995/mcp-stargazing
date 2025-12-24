from typing import Dict, Optional, Any
import asyncio
from src.server_instance import mcp
from src.celestial import celestial_pos, celestial_rise_set
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
