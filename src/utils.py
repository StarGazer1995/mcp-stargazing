from datetime import datetime

import pytz
from astropy import units as u
from astropy.coordinates import EarthLocation

from src.response import MCPError


def validate_coordinates(lat: float, lon: float) -> bool:
    """Validate latitude and longitude values."""
    return -90 <= lat <= 90 and -180 <= lon <= 180


def create_earth_location(lat: float, lon: float, elevation: float = 0.0) -> EarthLocation:
    """Create an EarthLocation object from coordinates."""
    if not validate_coordinates(lat, lon):
        raise MCPError(
            MCPError.INVALID_COORDINATES,
            f'Invalid coordinates: lat={lat}, lon={lon}',
            {'lat': lat, 'lon': lon, 'valid_range': {'lat': [-90, 90], 'lon': [-180, 180]}},
        )
    return EarthLocation(lat=lat * u.deg, lon=lon * u.deg, height=elevation * u.m)


def parse_time_string(time: str) -> datetime:
    """Parse a supported observation time string into a datetime object."""
    parsers = (
        lambda value: datetime.strptime(value, '%Y-%m-%d %H:%M:%S'),
        datetime.fromisoformat,
    )
    for parser in parsers:
        try:
            return parser(time)
        except ValueError:
            continue

    raise MCPError(
        MCPError.INVALID_TIME_FORMAT,
        f"Time string '{time}' matches neither '%Y-%m-%d %H:%M:%S' nor ISO format.",
        {'time_string': time, 'expected_formats': ['%Y-%m-%d %H:%M:%S', 'ISO format']},
    )


def ensure_timezone(dt: datetime, time_zone: str) -> datetime:
    """Attach the requested timezone when the input datetime is naive."""
    if dt.tzinfo is not None:
        return dt

    try:
        time_zone_info = pytz.timezone(time_zone)
    except pytz.exceptions.UnknownTimeZoneError as exc:
        raise MCPError(
            MCPError.INVALID_TIMEZONE,
            f"Invalid timezone '{time_zone}': {exc}",
            {'timezone': time_zone},
        ) from exc
    return time_zone_info.localize(dt)


def parse_observation_time(time: str, time_zone: str) -> datetime:
    """Parse and normalize an observation timestamp into a timezone-aware datetime."""
    return ensure_timezone(parse_time_string(time), time_zone)


def parse_datetime(date_str: str, time_str: str, timezone: str = 'UTC') -> datetime:
    """
    Parse a date string into a timezone-aware datetime object.
    Note: Uses `pytz.timezone` for compatibility, but avoids direct comparison of tzinfo objects.
    """
    try:
        tz = pytz.timezone(timezone)
        naive_dt = datetime.strptime(date_str, '%Y-%m-%d')
        return tz.localize(naive_dt)
    except (ValueError, pytz.exceptions.UnknownTimeZoneError) as e:
        raise MCPError(
            MCPError.INVALID_TIMEZONE, f"Invalid timezone '{timezone}': {e}", {'timezone': timezone}
        )


def localtime_to_utc(local_dt: datetime) -> datetime:
    """
    Convert a timezone-aware local datetime to UTC.
    Args:
        local_dt: Timezone-aware datetime object (e.g., from `parse_datetime`).
    Returns:
        datetime: UTC datetime (timezone-aware).
    Raises:
        MCPError: If input datetime is naive (not timezone-aware).
    """
    if local_dt.tzinfo is None:
        raise MCPError(
            MCPError.INVALID_TIME_FORMAT,
            'Input datetime must be timezone-aware.',
            {'received_tzinfo': None},
        )
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
        raise ValueError('Datetime object must be timezone-aware')

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
    lon: float, lat: float, time: str, time_zone: str
) -> tuple[EarthLocation, datetime]:
    """Process location and time inputs into standardized formats.

    Args:
        lon: Longitude in degrees
        lat: Latitude in degrees
        time: Time string (ISO format or "YYYY-MM-DD HH:MM:SS")
        time_zone: IANA timezone string (e.g. "America/New_York")

    Returns:
        Tuple of (EarthLocation, datetime) objects. datetime is timezone-aware.
    """
    earth_location = create_earth_location(lat=lat, lon=lon)
    return earth_location, parse_observation_time(time, time_zone)
