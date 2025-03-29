from fastmcp import FastMCP
from .celestial import celestial_pos, celestial_rise_set
from typing import Tuple, Optional
import datetime
from astropy.time import Time
from astropy.coordinates import EarthLocation
import astropy.units as u
import pytz

# Initialize MCP instance
mcp = FastMCP("mcp-stargazing")

def process_location_and_time(
    lon: float,
    lat: float,
    time: str,
    time_zone: str
) -> Tuple[EarthLocation, Time]:
    """Process location and time inputs into standardized formats.

    Args:
        lon: Longitude in degrees
        lat: Latitude in degrees
        time: Time string in format "YYYY-MM-DD HH:MM:SS"
        time_zone: IANA timezone string (e.g. "America/New_York")

    Returns:
        Tuple of (EarthLocation, Time) objects
    """
    earth_location = EarthLocation(lon=lon*u.deg, lat=lat*u.deg)
    time = datetime.datetime.strptime(time, "%Y-%m-%d %H:%M:%S")
    time_zone_info = pytz.timezone(time_zone)
    time = time_zone_info.localize(time)
    return earth_location, time

@mcp.tool()
def get_celestial_pos(
    celestial_object: str,
    lon: float,
    lat: float,
    time: str,
    time_zone: str
) -> Tuple[float, float]:
    """Calculate the altitude and azimuth angles of a celestial object.

    Args:
        celestial_object: Name of object (e.g. "sun", "moon", "andromeda")
        lon: Observer longitude in degrees
        lat: Observer latitude in degrees
        time: Observation time string "YYYY-MM-DD HH:MM:SS"
        time_zone: IANA timezone string

    Returns:
        Tuple of (altitude_degrees, azimuth_degrees)
    """
    location, time_info = process_location_and_time(lon, lat, time, time_zone)
    return celestial_pos(celestial_object, location, time_info)

@mcp.tool()
def get_celestial_rise_set(
    celestial_object: str,
    lon: float,
    lat: float,
    time: str,
    time_zone: str
) -> Tuple[Optional[Time], Optional[Time]]:
    """Calculate the rise and set times of a celestial object.

    Args:
        celestial_object: Name of object (e.g. "sun", "moon", "andromeda")
        lon: Observer longitude in degrees
        lat: Observer latitude in degrees
        time: Date string "YYYY-MM-DD HH:MM:SS"
        time_zone: IANA timezone string

    Returns:
        Tuple of (rise_time, set_time) as UTC Time objects
    """
    location, time_info = process_location_and_time(lon, lat, time, time_zone)
    return celestial_rise_set(celestial_object, location, time_info)

def main():
    """Run the MCP server."""
    mcp.run()

if __name__ == "__main__":
    main()