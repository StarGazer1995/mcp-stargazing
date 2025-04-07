from fastmcp import FastMCP
from .celestial import celestial_pos, celestial_rise_set
from .light_pollution import get_bortle_scale_light_pollution_given_location
from .qweather_interaction import qweather_get_weather_by_name, qweather_get_weather_by_position
import tzlocal
from typing import Tuple, Optional
import datetime
from astropy.time import Time
from astropy.coordinates import EarthLocation
import astropy.units as u
import pytz
import os

# Initialize MCP instance
mcp = FastMCP("mcp-stargazing")

def datetime_to_longitude(dt: datetime) -> float:
    """
    Calculate the longitude from a timezone-aware datetime object.
    
    Args:
        dt (datetime): A timezone-aware datetime object.
    
    Returns:
        float: The longitude in degrees.
    
    Raises:
        ValueError: If the datetime is not timezone-aware.
    """
    if dt.tzinfo is None:
        raise ValueError("Datetime object must be timezone-aware")
    
    # Get the UTC offset (as a timedelta)
    utc_offset = dt.utcoffset()
    if utc_offset is None:
        return 0.0  # UTC
    
    # Convert timedelta to total hours (including fractional hours)
    total_seconds = utc_offset.total_seconds()
    total_hours = total_seconds / 3600
    
    # Calculate longitude (15 degrees per hour)
    longitude = total_hours * 15
    
    return longitude

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
    replace_lon = datetime_to_longitude(time)
    location.replace(lon=replace_lon*u.deg)
    return celestial_rise_set(celestial_object, location, time_info)

@mcp.tool()
def get_light_pollution(
    lon: float,
    lat: float,
    radius_km: float = 10.0
) -> float:
    """Get the Bortle scale light pollution for a given location.
    Args:
        lon: Observer longitude in degrees
        lat: Observer latitude in degrees
        radius_km: Radius in km to average over
    """
    map_path = os.getenv("LIGHT_POLLUTION_MAP_PATH", None)
    if (map_path is None) or (not os.path.exists(map_path)):
        raise ValueError("Light pollution map path not found")
    return get_bortle_scale_light_pollution_given_location(
        lat=lat,
        lon=lon,
        raster_path=map_path,
        radius_km=radius_km,
    )

@mcp.tool()
def get_local_datetime_info():
    """
    Retrieve the current datetime and timezone.

    Returns:
        str: A string representation of the current datetime with timezone,
             formatted as "YYYY-MM-DD HH:MM:SS.SSSSSS+HH:MM" (ISO format).
             Example: "2023-11-15 14:30:45.123456+05:30".

    Note:
        - Delegates to `utils.get_datetime()` for implementation.
        - The output matches `str(datetime.now(timezone))`.
    """
    local_timezone = tzlocal.get_localzone()  # Automatically detect the local timezone
    tz = pytz.timezone(zone=str(local_timezone))
    current_time = datetime.datetime.now(tz)
    return str(current_time)

@mcp.tool()
def get_weather_by_name(place_name: str):
    """
    Fetches weather data for a specified location by its name using the QWeather API.

    Args:
        place_name (str): The name of the location (e.g., city, region) for which weather data is requested.

    Returns:
        The weather data returned by the QWeather API for the specified location.

    Raises:
        ValueError: If the `QWEATHER_API_KEY` environment variable is not set, preventing API access.
    """
    QWEATHER_API_KEY = os.getenv("QWEATHER_API_KEY", None)
    if QWEATHER_API_KEY is None:
        raise ValueError("QWEATHER_API_KEY environment variable not set.")
    return qweather_get_weather_by_name(place_name, QWEATHER_API_KEY)

@mcp.tool()
def get_weather_by_position(lat: float, lon: float):
    """
    Fetches weather data for a specified location by its geographic coordinates (latitude and longitude) using the QWeather API.

    Args:
        lat (float): The latitude of the location for which weather data is requested.
        lon (float): The longitude of the location for which weather data is requested.

    Returns:
        The weather data returned by the QWeather API for the specified coordinates.

    Raises:
        ValueError: If the `QWEATHER_API_KEY` environment variable is not set, preventing API access.
    """
    QWEATHER_API_KEY = os.getenv("QWEATHER_API_KEY", None)
    if QWEATHER_API_KEY is None:
        raise ValueError("QWEATHER_API_KEY environment variable not set.")
    return qweather_get_weather_by_position(lat, lon, QWEATHER_API_KEY)

def main():
    """Run the MCP server."""
    mcp.run()

if __name__ == "__main__":
    main()