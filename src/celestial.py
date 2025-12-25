from astropy.time import Time
from astropy.coordinates import (
    EarthLocation,
    AltAz,
    get_sun,
    get_body,
    SkyCoord,
    GeocentricTrueEcliptic,
    get_constellation
)
import astropy.units as u
from typing import Optional, Tuple, Union, Dict, Any
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

def calculate_moon_info(time: Union[Time, datetime]) -> Dict[str, Any]:
    """
    Calculate detailed information about the Moon's phase and position.
    
    Args:
        time: Observation time (Astropy Time or timezone-aware datetime).
        
    Returns:
        Dict containing:
        - illumination: Fraction of the moon illuminated (0.0 to 1.0)
        - phase_name: String description of the phase (e.g. "Waxing Gibbous")
        - age_days: Approximate age of the moon in days (since New Moon)
        - elongation: Angular separation from Sun in degrees
        - earth_distance: Distance from Earth in km
    """
    # Convert local time to UTC if input is datetime
    if isinstance(time, datetime):
        if time.tzinfo is None:
            raise ValueError("Input datetime must be timezone-aware for local time.")
        time = Time(time.astimezone(pytz.UTC))

    sun = get_sun(time)
    moon = get_body("moon", time)

    # Elongation (angular separation)
    elongation = sun.separation(moon)
    
    # Illumination fraction (0-1)
    # The illuminated fraction k is given by k = (1 - cos(i))/2 where i is phase angle (approx elongation)
    # New Moon (0 deg): (1 - 1)/2 = 0
    # Full Moon (180 deg): (1 - (-1))/2 = 1
    illumination = (1 - np.cos(elongation.rad)) / 2.0
    
    # Phase angle for naming (requires Ecliptic longitude)
    sun_ecl = sun.transform_to(GeocentricTrueEcliptic(obstime=time))
    moon_ecl = moon.transform_to(GeocentricTrueEcliptic(obstime=time))
    
    # Calculate longitude difference (Moon - Sun)
    lon_diff = (moon_ecl.lon.deg - sun_ecl.lon.deg) % 360
    
    # Determine Phase Name
    # New Moon: 0
    # First Quarter: 90
    # Full Moon: 180
    # Last Quarter: 270
    
    if lon_diff < 1 or lon_diff > 359:
        phase_name = "New Moon"
    elif 1 <= lon_diff < 89:
        phase_name = "Waxing Crescent"
    elif 89 <= lon_diff <= 91:
         phase_name = "First Quarter"
    elif 91 < lon_diff < 179:
        phase_name = "Waxing Gibbous"
    elif 179 <= lon_diff <= 181:
        phase_name = "Full Moon"
    elif 181 < lon_diff < 269:
        phase_name = "Waning Gibbous"
    elif 269 <= lon_diff <= 271:
        phase_name = "Last Quarter"
    else:
        phase_name = "Waning Crescent"

    # Age in days (approximate)
    # Synodic month is ~29.53 days. Age = (lon_diff / 360) * 29.53
    age_days = (lon_diff / 360.0) * 29.53059
    
    return {
        "illumination": float(illumination),
        "phase_name": phase_name,
        "age_days": float(age_days),
        "elongation": float(elongation.deg),
        "earth_distance": float(moon.distance.to(u.km).value)
    }

def get_visible_planets(
    observer_location: EarthLocation,
    time: Union[Time, datetime]
) -> list[Dict[str, Any]]:
    """
    Get a list of planets currently above the horizon.
    
    Args:
        observer_location: Observer's EarthLocation.
        time: Observation time.
        
    Returns:
        List of dicts containing planet name, altitude, azimuth, and magnitude (if available).
    """
    # Convert local time to UTC if input is datetime
    if isinstance(time, datetime):
        if time.tzinfo is None:
            raise ValueError("Input datetime must be timezone-aware for local time.")
        time = Time(time.astimezone(pytz.UTC))

    planets = ["mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune"]
    visible_planets = []
    
    for planet in planets:
        # Get coordinates
        obj_coord = get_body(planet, time)
        altaz_frame = AltAz(obstime=time, location=observer_location)
        altaz = obj_coord.transform_to(altaz_frame)
        
        # Check if above horizon
        if altaz.alt.deg > 0:
            visible_planets.append({
                "name": planet.capitalize(),
                "altitude": float(altaz.alt.deg),
                "azimuth": float(altaz.az.deg),
                "constellation": None # Placeholder for future implementation
            })
            
    return visible_planets

def get_constellation_center(
    constellation_name: str,
    observer_location: EarthLocation,
    time: Union[Time, datetime]
) -> Dict[str, Any]:
    """
    Get the position (altitude/azimuth) of the center of a constellation.
    Uses Simbad to resolve the constellation name to a central coordinate.
    
    Args:
        constellation_name: Name of constellation (e.g. "Orion", "Ursa Major")
        observer_location: Observer's EarthLocation
        time: Observation time
        
    Returns:
        Dict with keys: name, altitude, azimuth
    """
    # Convert local time to UTC if input is datetime
    if isinstance(time, datetime):
        if time.tzinfo is None:
            raise ValueError("Input datetime must be timezone-aware for local time.")
        time = Time(time.astimezone(pytz.UTC))

    # Resolve constellation center
    # Simbad often resolves constellation names to their approximate center
    try:
        # Some constellation names (e.g. "Ursa Major") might not resolve directly in Simbad as an object.
        # If standard resolution fails, try adding "Constellation" or using a major star.
        try:
            center_coord = _resolve_simbad_object(constellation_name)
        except (ValueError, IndexError):
            # Fallback map for common constellations if Simbad fails
            FALLBACK_STARS = {
                "Ursa Major": "Alioth",
                "Ursa Minor": "Polaris",
                "Cassiopeia": "Schedar",
                "Southern Cross": "Acrux",
                "Crux": "Acrux",
                "Orion": "Betelgeuse",
                "Scorpius": "Antares",
                "Leo": "Regulus",
                "Gemini": "Pollux",
                "Taurus": "Aldebaran",
                "Canis Major": "Sirius"
            }
            if constellation_name in FALLBACK_STARS:
                print(f"[DEBUG] Falling back to star '{FALLBACK_STARS[constellation_name]}' for '{constellation_name}'")
                center_coord = _resolve_simbad_object(FALLBACK_STARS[constellation_name])
            else:
                 raise
                 
    except Exception as e:
        raise ValueError(f"Could not resolve constellation '{constellation_name}': {str(e)}")

    altaz_frame = AltAz(obstime=time, location=observer_location)
    altaz = center_coord.transform_to(altaz_frame)
    
    return {
        "name": constellation_name,
        "altitude": float(altaz.alt.deg),
        "azimuth": float(altaz.az.deg)
    }

import json
import os

OBJECTS_CACHE = None

def _load_objects():
    global OBJECTS_CACHE
    if OBJECTS_CACHE is not None:
        return OBJECTS_CACHE
        
    data_path = os.path.join(os.path.dirname(__file__), 'data/objects.json')
    try:
        with open(data_path, 'r') as f:
            OBJECTS_CACHE = json.load(f)
    except FileNotFoundError:
        OBJECTS_CACHE = [] # Should handle gracefully
        print(f"Warning: Objects data file not found at {data_path}")
        
    return OBJECTS_CACHE

def calculate_nightly_forecast(
    observer_location: EarthLocation,
    date: datetime,
    limit: int = 50
) -> Dict[str, Any]:
    """
    Generate a curated list of best objects to view for a given night.
    Accounts for Moon phase/position and light pollution interference.
    """
    # 1. Setup Time
    if date.tzinfo is None:
         raise ValueError("Input datetime must be timezone-aware.")
    
    # Ensure we are looking at "Night" (e.g. 10 PM local)
    # Actually, we should check availability throughout the night.
    # For simplicity, we calculate LST at local midnight.
    
    # Calculate Midnight
    # date is the user's requested date/time. 
    # If it's daytime, we assume they want the UPCOMING night.
    # If it's night, we use current night.
    
    time = Time(date)
    
    # 2. Moon Info
    moon_info = calculate_moon_info(date)
    moon_illum = moon_info['illumination']
    moon_coord = get_body("moon", time)
    
    # 3. Planets (Always Highlights)
    planets = get_visible_planets(observer_location, time)
    
    # 4. Deep Sky Objects
    raw_objects = _load_objects()
    candidates = []
    
    # LST Calculation for rough filtering
    # Sidereal time is roughly RA on meridian.
    lst = time.sidereal_time('mean', longitude=observer_location.lon)
    lst_deg = lst.deg
    
    # Visibility Window: Objects with RA within +/- 6 hours (90 deg) of LST are generally "up"
    # We can be generous: +/- 8 hours (120 deg)
    
    for obj in raw_objects:
        # Check Catalog/Magnitude
        mag = obj.get('magnitude', 99.9)
        catalog = obj.get('catalog', 'Unknown')
        
        # Strict Filter: Exclude faint NGC
        if catalog == 'NGC' and mag > 10.0:
            continue
            
        # LST Filter (RA is in degrees in our JSON)
        obj_ra = obj['ra']
        
        # Calculate smallest difference between RA and LST (in degrees)
        # Note: 360 degrees = 24 hours. 1 hour = 15 degrees.
        diff = abs(obj_ra - lst_deg)
        if diff > 180: diff = 360 - diff
        
        # DEBUG: Print LST and diff for M42 and M13
        # if obj['name'] in ['M 42', 'M 13']:
        #    print(f"DEBUG: {obj['name']} RA={obj_ra}, LST={lst_deg}, Diff={diff}")
        
        if diff > 120: # ~8 hours
             continue
             
        # Create Candidate
        candidates.append(obj)
        
    # Detailed Scoring
    scored_objects = []
    
    altaz_frame = AltAz(obstime=time, location=observer_location)
    
    for obj in candidates:
        # Coordinate
        # Ensure RA/Dec are valid floats
        try:
            ra_val = float(obj['ra'])
            dec_val = float(obj['dec'])
        except (ValueError, TypeError):
            continue
            
        coord = SkyCoord(ra=ra_val*u.deg, dec=dec_val*u.deg, frame='icrs')
        altaz = coord.transform_to(altaz_frame)
        alt = altaz.alt.deg
        
        if alt < 20: # Too low
            continue
            
        mag = obj.get('magnitude', 99.9)
        
        # Moon Penalty
        # Separation
        sep = coord.separation(moon_coord).deg
        
        effective_mag = mag
        
        if moon_illum > 0.1 and altaz.alt.deg > 0: # If Moon is up and bright
             if sep < 15:
                 # Too close to moon, skip
                 continue
             elif sep < 60:
                 # Penalty: Add to magnitude (make it seem fainter)
                 # Max penalty at 15 deg: (60-15)*0.1 = 4.5 mag penalty
                 # Min penalty at 60 deg: 0
                 penalty = (60 - sep) * 0.1
                 effective_mag += penalty
        
        # Base Score (lower is better, like magnitude)
        # We subtract altitude bonus (higher alt = better)
        # Bonus: 1 mag equivalent per 30 degrees altitude?
        alt_bonus = (alt / 90.0) * 2.0 
        
        score = effective_mag - alt_bonus
        
        # Messier Bonus (Ensure they float to top)
        if obj.get('catalog') == 'Messier':
            score -= 5.0 
            
        scored_objects.append({
            "name": obj['name'],
            "type": obj['type'],
            "magnitude": mag,
            "altitude": round(alt, 1),
            "azimuth": round(altaz.az.deg, 1),
            "catalog": obj.get('catalog', 'Unknown'),
            "score": score
        })
        
    # Sort
    scored_objects.sort(key=lambda x: x['score'])
    
    # Trim
    top_objects = scored_objects[:limit]
    
    return {
        "moon_phase": moon_info,
        "planets": planets,
        "deep_sky": top_objects
    }

def identify_constellation(
    sky_coord: SkyCoord
) -> str:
    """Identify which constellation a coordinate belongs to."""
    return get_constellation(sky_coord)

from functools import lru_cache

@lru_cache(maxsize=128)
def _resolve_simbad_object(name: str) -> SkyCoord:
    """Resolve deep-space object name to SkyCoord using SIMBAD with caching."""
    print(f"[DEBUG] Resolving object '{name}' via Simbad...")
    # Query SIMBAD for the object
    # Note: Simbad query involves network request which can be SLOW.
    result = Simbad.query_object(name)
    if result is None:
        # Try capitalizing first letter (e.g. "sirius" -> "Sirius")
        print(f"[DEBUG] '{name}' not found, trying '{name.capitalize()}'...")
        result = Simbad.query_object(name.capitalize())
    
    if result is None:
         print(f"[DEBUG] Object '{name}' not found in Simbad.")
         raise ValueError(f"Object '{name}' not found in SIMBAD.")
    
    print(f"[DEBUG] Successfully resolved '{name}'.")
    
    # Check if we got any results
    if len(result) == 0:
        raise ValueError(f"Simbad returned empty result for '{name}'.")
        
    # Extract RA and Dec from the query result
    ra = result["ra"][0]
    dec = result["dec"][0]
    return SkyCoord(ra, dec, unit=(u.hourangle, u.deg), frame='icrs')

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
        return _resolve_simbad_object(name)
    
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
