from astropy import units as u
from astropy.coordinates import EarthLocation
from datetime import datetime
import pytz
import tzlocal
from typing import Tuple

def validate_coordinates(lat: float, lon: float) -> bool:
    """Validate latitude and longitude values."""
    return -90 <= lat <= 90 and -180 <= lon <= 180

def create_earth_location(lat: float, lon: float, elevation: float = 0.0) -> EarthLocation:
    """Create an EarthLocation object from coordinates."""
    if not validate_coordinates(lat, lon):
        raise ValueError(f"Invalid coordinates: lat={lat}, lon={lon}")
    return EarthLocation(lat=lat * u.deg, lon=lon * u.deg, height=elevation * u.m)

def parse_datetime(date_str: str, time_str: str, timezone: str = "UTC") -> datetime:
    """
    Parse a date string into a timezone-aware datetime object.
    Note: Uses `pytz.timezone` for compatibility, but avoids direct comparison of tzinfo objects.
    """
    try:
        tz = pytz.timezone(timezone)
        naive_dt = datetime.strptime(date_str, "%Y-%m-%d")
        return tz.localize(naive_dt)
    except (ValueError, pytz.exceptions.UnknownTimeZoneError) as e:
        raise ValueError(f"Invalid input: {e}")

def localtime_to_utc(local_dt: datetime) -> datetime:
    """
    Convert a timezone-aware local datetime to UTC.
    Args:
        local_dt: Timezone-aware datetime object (e.g., from `parse_datetime`).
    Returns:
        datetime: UTC datetime (timezone-aware).
    Raises:
        ValueError: If input datetime is naive (not timezone-aware).
    """
    if local_dt.tzinfo is None:
        raise ValueError("Input datetime must be timezone-aware.")
    return local_dt.astimezone(pytz.UTC)

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
) -> Tuple[EarthLocation, datetime]:
    """Process location and time inputs into standardized formats.

    Args:
        lon: Longitude in degrees
        lat: Latitude in degrees
        time: Time string (ISO format or "YYYY-MM-DD HH:MM:SS")
        time_zone: IANA timezone string (e.g. "America/New_York")

    Returns:
        Tuple of (EarthLocation, datetime) objects. datetime is timezone-aware.
    """
    earth_location = EarthLocation(lon=lon*u.deg, lat=lat*u.deg)
    
    try:
        # Try standard format first
        dt = datetime.strptime(time, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            # Try ISO format
            dt = datetime.fromisoformat(time)
        except ValueError:
             raise ValueError(f"Time string '{time}' matches neither '%Y-%m-%d %H:%M:%S' nor ISO format.")

    # If datetime is naive, localize it using the provided time_zone
    if dt.tzinfo is None:
        time_zone_info = pytz.timezone(time_zone)
        dt = time_zone_info.localize(dt)
    else:
        # If already aware, ensure it's in the requested timezone or leave as is?
        # Usually we trust the input timezone if provided separately, 
        # but if the string has offset, that takes precedence.
        # Here we follow the original logic's intent: ensure awareness.
        pass

    return earth_location, dt
