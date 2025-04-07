from astropy.time import Time
from astropy.coordinates import (
    EarthLocation,
    AltAz,
    get_sun,
    get_body,
    SkyCoord
)
import astropy.units as u
from typing import Optional, Tuple, Union
from datetime import datetime
import numpy as np
import pytz
from astroquery.simbad import Simbad

def celestial_pos(
    celestial_object: str,
    observer_location: EarthLocation,
    time: Union[Time, datetime]
) -> Tuple[float, float]:
    """
    Calculate the altitude and azimuth angles of a celestial object.
    Args:
        celestial_object: Name of the object ("sun", "moon", or planet name).
        observer_location: Observer's EarthLocation.
        time: Observation time (Astropy Time or timezone-aware datetime in LOCAL TIME).
    Returns:
        Tuple[float, float]: (altitude_degrees, azimuth_degrees).
        - Altitude: Elevation above the horizon (0° = horizon, 90° = zenith).
        - Azimuth: Compass direction (0° = North, 90° = East).
    Raises:
        ValueError: If the object is not supported or time is naive.
    """
    # Convert local time to UTC if input is datetime
    if isinstance(time, datetime):
        if time.tzinfo is None:
            raise ValueError("Input datetime must be timezone-aware for local time.")
        time = Time(time.astimezone(pytz.UTC))  # Convert to UTC
    
    obj_coord = _get_celestial_object(celestial_object, time)
    altaz_frame = AltAz(obstime=time, location=observer_location)
    altaz = obj_coord.transform_to(altaz_frame)
    return altaz.alt.deg, altaz.az.deg  # Return (altitude, azimuth)

def celestial_rise_set(
    celestial_object: str,
    observer_location: EarthLocation,
    date: datetime,
    horizon: float = 0.0
) -> Tuple[Optional[Time], Optional[Time]]:
    """
    Calculate rise and set times of a celestial object.
    Args:
        celestial_object: Name of the object ("sun", "moon", or planet name).
        observer_location: Observer's EarthLocation.
        date: Date for calculation (timezone-aware datetime).
        horizon: Horizon elevation in degrees (default: 0).
    Returns:
        Tuple[Optional[Time], Optional[Time]]: (rise_time, set_time) in UTC.
    Raises:
        ValueError: If the object is not supported or horizon is invalid.
    """
    if not -90 <= horizon <= 90:
        raise ValueError("Horizon must be between -90 and 90 degrees.")
    time_zone = pytz.timezone(zone=str(date.tzinfo))
    origin_zone = pytz.timezone(zone='UTC')
    time_grid = _generate_time_grid(date)
    altitudes = np.array([
        celestial_pos(celestial_object, observer_location, t)[0]
        for t in time_grid
    ])
    def __convert_timezone(time):
        t = time.to_datetime()
        t = origin_zone.localize(t)
        return t.astimezone(time_zone)
    
    rise_idx, set_idx = _find_rise_set_indices(altitudes, horizon)
    rise_time = __convert_timezone(time_grid[rise_idx]) if rise_idx is not None else None
    set_time = __convert_timezone(time_grid[set_idx]) if set_idx is not None else None
    return rise_time, set_time

def _get_celestial_object(name: str, time: Time) -> SkyCoord:
    """Resolve a celestial object name to its SkyCoord.
    Supports:
    - Solar system objects (sun, moon, planets)
    - Stars (e.g., "sirius")
    - Deep-space objects (e.g., "andromeda", "orion_nebula")
    """
    name = name.lower()
    
    # Solar system objects
    if name == "sun":
        return get_sun(time)
    elif name == "moon":
        return get_body("moon", time)
    elif name in ["mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune"]:
        return get_body(name, time)
    
    # Deep-space objects (stars, galaxies, nebulae)
    try:
        # Query SIMBAD for the object
        result = Simbad.query_object(name)
        if result is None:
            raise ValueError(f"Object '{name}' not found in SIMBAD.")
        
        # Extract RA and Dec from the query result
        ra = result["ra"][0]
        dec = result["dec"][0]
        return SkyCoord(ra, dec, unit=(u.hourangle, u.deg), frame='icrs')
    
    except Exception as e:
        raise ValueError(f"Failed to resolve object '{name}': {str(e)}")
    
def _generate_time_grid(date: datetime) -> Time:
    """Generate a grid of Time objects for the given date (5-minute intervals)."""
    start = Time(date.replace(hour=0, minute=0, second=0))
    end = Time(date.replace(hour=23, minute=59, second=59))
    return start + np.linspace(0, 1, 288) * (end - start)  # 288 = 24h / 5min

def _find_rise_set_indices(
    altitudes: np.ndarray,
    horizon: float
) -> Tuple[Optional[int], Optional[int]]:
    """Find indices where altitude crosses the horizon."""
    above = altitudes > horizon
    crossings = np.where(np.diff(above))[0]
    rise_idx = crossings[0] if len(crossings) > 0 else None
    set_idx = crossings[-1] if len(crossings) > 1 else None
    return rise_idx, set_idx
