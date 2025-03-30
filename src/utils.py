from astropy import units as u
from astropy.coordinates import EarthLocation
from datetime import datetime
import pytz
import tzlocal

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