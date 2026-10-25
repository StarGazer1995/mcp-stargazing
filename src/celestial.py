import json
import os
import threading
from datetime import datetime, timedelta
from importlib import resources
from typing import Any

import astropy.units as u
import numpy as np
import pytz
from astropy.coordinates import (
    AltAz,
    EarthLocation,
    SkyCoord,
    get_body,
    get_sun,
    solar_system_ephemeris,
)
from astropy.time import Time
from astroquery.simbad import Simbad
from stargazing_core import (
    calculate_moon_info,
    get_moon_altaz,  # noqa: F401 — re-exported for impl.py
    get_visible_planets,
    identify_constellation,  # noqa: F401 — re-exported for external use
)
from stargazing_core import (
    filter_candidates_by_lst as _filter_candidates_by_lst,
)
from stargazing_core import (
    score_deep_sky_objects as _score_deep_sky_objects,
)

from src.logging_config import get_logger
from src.schemas.celestial import NightWindow

logger = get_logger(__name__)

solar_system_ephemeris.set('builtin')


def celestial_pos(
    celestial_object: str, observer_location: EarthLocation, time: Time | datetime
) -> tuple[float, float]:
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
            raise ValueError('Input datetime must be timezone-aware for local time.')
        time = Time(time.astimezone(pytz.UTC))  # Convert to UTC

    obj_coord = _get_celestial_object(celestial_object, time)
    altaz_frame = AltAz(obstime=time, location=observer_location)
    altaz = obj_coord.transform_to(altaz_frame)
    return altaz.alt.deg, altaz.az.deg  # Return (altitude, azimuth)


def celestial_rise_set(
    celestial_object: str,
    observer_location: EarthLocation,
    date: datetime,
    horizon: float = 0.0,
    event_scope: str = 'calendar_day',
) -> tuple[datetime | None, datetime | None]:
    """
    Calculate rise and set times of a celestial object.
    Args:
        celestial_object: Name of the object ("sun", "moon", or planet name).
        observer_location: Observer's EarthLocation.
        date: Date for calculation (timezone-aware datetime).
        horizon: Horizon elevation in degrees (default: 0).
        event_scope: ``calendar_day`` keeps the historical behavior and searches the
            full local calendar day containing ``date``. ``next_events`` searches
            forward from ``date`` for the next rise and next set independently.
    Returns:
        Tuple[Optional[datetime], Optional[datetime]]: localized rise/set datetimes.
    Raises:
        ValueError: If the event scope or horizon is invalid.
    """
    if not -90 <= horizon <= 90:
        raise ValueError('Horizon must be between -90 and 90 degrees.')
    if event_scope not in {'calendar_day', 'next_events'}:
        raise ValueError("event_scope must be 'calendar_day' or 'next_events'.")
    # Attempt to recover IANA timezone name; fall back to FixedOffset if unavailable.
    # str(date.tzinfo) can return e.g. 'UTC+08:00' which is not a valid IANA name.
    tz_str = str(date.tzinfo)
    try:
        time_zone = pytz.timezone(tz_str)
    except (pytz.UnknownTimeZoneError, KeyError):
        time_zone = date.tzinfo
    origin_zone = pytz.timezone(zone='UTC')
    time_grid = _generate_time_grid(date, event_scope=event_scope)
    name = celestial_object.lower()
    altaz_frame = AltAz(obstime=time_grid, location=observer_location)
    if name == 'sun':
        obj_coord = get_sun(time_grid)
    elif name == 'moon':
        obj_coord = get_body('moon', time_grid)
    elif name in ['mercury', 'venus', 'mars', 'jupiter', 'saturn', 'uranus', 'neptune']:
        obj_coord = get_body(name, time_grid)
    else:
        base_coord = _resolve_simbad_object(celestial_object)
        obj_coord = base_coord
    altaz = obj_coord.transform_to(altaz_frame)
    altitudes = np.array(altaz.alt.deg)

    def __convert_timezone(time):
        t = time.to_datetime()
        t = origin_zone.localize(t)
        return t.astimezone(time_zone)

    rise_idx, set_idx = _find_rise_set_indices(altitudes, horizon)
    rise_time = __convert_timezone(time_grid[rise_idx]) if rise_idx is not None else None
    set_time = __convert_timezone(time_grid[set_idx]) if set_idx is not None else None
    return rise_time, set_time


def calculate_civil_night_window(
    observer_location: EarthLocation,
    reference_time: datetime,
    *,
    civil_horizon: float = -6.0,
) -> NightWindow:
    """Return the civil-dark window containing or immediately following a reference time."""
    if reference_time.tzinfo is None:
        raise ValueError('Reference time must be timezone-aware.')

    try:
        time_zone = pytz.timezone(str(reference_time.tzinfo))
    except (pytz.UnknownTimeZoneError, KeyError):
        time_zone = reference_time.tzinfo

    offsets_hours = np.arange(-12, 36.5, 0.5)
    grid = Time([reference_time + timedelta(hours=float(hours)) for hours in offsets_hours])
    frame = AltAz(obstime=grid, location=observer_location)
    altitudes = np.asarray(get_sun(grid).transform_to(frame).alt.deg)
    above = altitudes > civil_horizon
    diff = np.diff(above.astype(int))
    dusk_indices = np.where(diff == -1)[0]
    dawn_indices = np.where(diff == 1)[0]

    pairs: list[tuple[float, float]] = []
    for dusk_idx in dusk_indices:
        dawn_idx = next((idx for idx in dawn_indices if idx > dusk_idx), None)
        if dawn_idx is None:
            continue
        dusk_fraction = (civil_horizon - altitudes[dusk_idx]) / (
            altitudes[dusk_idx + 1] - altitudes[dusk_idx]
        )
        dawn_fraction = (civil_horizon - altitudes[dawn_idx]) / (
            altitudes[dawn_idx + 1] - altitudes[dawn_idx]
        )
        dusk_unix = grid[dusk_idx].unix + dusk_fraction * (
            grid[dusk_idx + 1].unix - grid[dusk_idx].unix
        )
        dawn_unix = grid[dawn_idx].unix + dawn_fraction * (
            grid[dawn_idx + 1].unix - grid[dawn_idx].unix
        )
        pairs.append((float(dusk_unix), float(dawn_unix)))

    if not pairs:
        raise ValueError('No civil-dark window found in the 48-hour search range.')

    reference_unix = reference_time.timestamp()
    selected = next(
        (
            (dusk_unix, dawn_unix)
            for dusk_unix, dawn_unix in pairs
            if dusk_unix <= reference_unix < dawn_unix
        ),
        next(
            (
                (dusk_unix, dawn_unix)
                for dusk_unix, dawn_unix in pairs
                if dusk_unix >= reference_unix
            ),
            pairs[0],
        ),
    )
    dusk, dawn = (
        datetime.fromtimestamp(value, tz=pytz.UTC).astimezone(time_zone) for value in selected
    )
    return NightWindow(
        local_date=dusk.date().isoformat(),
        civil_dusk=dusk.isoformat(),
        civil_dawn=dawn.isoformat(),
        duration_hours=round((dawn - dusk).total_seconds() / 3600.0, 2),
        time_zone=str(time_zone),
    )


# calculate_moon_info is re-exported from stargazing_core (imported at top of file)


# get_moon_altaz is re-exported from stargazing_core (imported at top of file)


# get_visible_planets is re-exported from stargazing_core (imported at top of file)


def get_constellation_center(
    constellation_name: str, observer_location: EarthLocation, time: Time | datetime
) -> dict[str, Any]:
    """
    Return the apparent Alt/Az of a constellation's representative center using local data.
    """
    # Convert local time to UTC if input is datetime
    if isinstance(time, datetime):
        if time.tzinfo is None:
            raise ValueError('Input datetime must be timezone-aware for local time.')
        time = Time(time.astimezone(pytz.UTC))

    centers = _load_constellation_centers()
    centers_map = {item['name'].lower(): item for item in centers}
    key = constellation_name.lower()
    if key in centers_map:
        ra = float(centers_map[key]['ra'])
        dec = float(centers_map[key]['dec'])
        center_coord = SkyCoord(ra=ra * u.deg, dec=dec * u.deg, frame='icrs')
    else:
        fallback = {
            'ursa major': 'Alioth',
            'ursa minor': 'Polaris',
            'cassiopeia': 'Schedar',
            'southern cross': 'Acrux',
            'crux': 'Acrux',
            'orion': 'Betelgeuse',
            'scorpius': 'Antares',
            'leo': 'Regulus',
            'gemini': 'Pollux',
            'taurus': 'Aldebaran',
            'canis major': 'Sirius',
        }
        if key in fallback:
            center_coord = _resolve_simbad_object(fallback[key])
        else:
            center_coord = _resolve_simbad_object(constellation_name)

    altaz_frame = AltAz(obstime=time, location=observer_location)
    altaz = center_coord.transform_to(altaz_frame)

    return {
        'name': constellation_name,
        'altitude': float(altaz.alt.deg),
        'azimuth': float(altaz.az.deg),
    }


OBJECTS_CACHE = None
CONSTELLATIONS_CACHE = None
_objects_lock = threading.Lock()
_constellations_lock = threading.Lock()


def _load_data_resource(filename: str) -> list[dict[str, Any]]:
    """Load packaged JSON data from the `src/data` resource directory."""
    resource = resources.files('src').joinpath('data').joinpath(filename)
    return json.loads(resource.read_text(encoding='utf-8'))


def _load_objects():
    global OBJECTS_CACHE
    if OBJECTS_CACHE is not None:
        return OBJECTS_CACHE

    with _objects_lock:
        # Double-check: another thread may have loaded while we waited for the lock
        if OBJECTS_CACHE is not None:
            return OBJECTS_CACHE

        data_path = os.path.join(os.path.dirname(__file__), 'data/objects.json')
        try:
            OBJECTS_CACHE = _load_data_resource('objects.json')
        except FileNotFoundError:
            OBJECTS_CACHE = []  # Should handle gracefully
            logger.warning('Objects data file not found at %s', data_path)

    return OBJECTS_CACHE


def _load_constellation_centers():
    global CONSTELLATIONS_CACHE
    if CONSTELLATIONS_CACHE is not None:
        return CONSTELLATIONS_CACHE

    with _constellations_lock:
        if CONSTELLATIONS_CACHE is not None:
            return CONSTELLATIONS_CACHE

        try:
            CONSTELLATIONS_CACHE = _load_data_resource('constellation_centers.json')
        except FileNotFoundError:
            CONSTELLATIONS_CACHE = []

    return CONSTELLATIONS_CACHE


# _filter_candidates_by_lst is re-exported from stargazing_core (imported at top)
# _score_deep_sky_objects is re-exported from stargazing_core (imported at top)


def calculate_nightly_forecast(
    observer_location: EarthLocation, date: datetime, limit: int = 50
) -> dict[str, Any]:
    """Generate a curated list of best objects to view for a given night.

    Pipeline: time validation → moon/planet data → LST coarse filter →
    detailed altitude+moon-glare scoring → sort & trim.
    """
    if date.tzinfo is None:
        raise ValueError('Input datetime must be timezone-aware.')

    time = Time(date)

    # 1. Moon and planet context
    moon_info = calculate_moon_info(date)
    moon_coord = get_body('moon', time)
    planets = get_visible_planets(observer_location, time)

    # 2. Coarse LST filter — keep only objects near the meridian
    lst = time.sidereal_time('mean', longitude=observer_location.lon)
    raw_objects = _load_objects()
    candidates = _filter_candidates_by_lst(raw_objects, lst.deg)

    # 3. Fine-grained scoring with altitude and moon-glare
    scored_objects = _score_deep_sky_objects(
        candidates, time, observer_location, moon_coord, moon_info['illumination']
    )

    # Enrich with catalog data (angular size) and transit estimate
    _obj_index = {o['name']: o for o in raw_objects}
    for obj in scored_objects[:limit]:
        orig = _obj_index.get(obj['name'])
        if orig:
            obj['angular_size_arcmin'] = orig.get('angular_size_maj_arcmin')
            # The altitude at scoring time (near midnight) ≈ transit altitude
            obj['transit_alt'] = obj.get('altitude')

    return {
        'moon_phase': moon_info,
        'planets': planets,
        'deep_sky': scored_objects[:limit],
    }


# identify_constellation is re-exported from stargazing_core (imported at top of file)


_simbad_cache: dict[str, SkyCoord] = {}
_simbad_cache_lock = threading.Lock()


def _resolve_simbad_object(name: str) -> SkyCoord:
    """Resolve deep-space object name to SkyCoord using SIMBAD with caching.

    Only caches successful results — transient network errors are NOT cached,
    unlike ``@lru_cache`` which would permanently poison the cache.
    """
    # Fast path: cache hit (no lock needed for read-only check, and SkyCoord
    # objects are immutable once constructed)
    cached = _simbad_cache.get(name)
    if cached is not None:
        return cached

    logger.debug("Resolving object '%s' via Simbad...", name)
    # Query SIMBAD for the object
    # Note: Simbad query involves network request which can be SLOW.
    result = Simbad.query_object(name)
    if result is None:
        # Try capitalizing first letter (e.g. "sirius" -> "Sirius")
        logger.debug("'%s' not found, trying '%s'...", name, name.capitalize())
        result = Simbad.query_object(name.capitalize())

    if result is None:
        logger.debug("Object '%s' not found in Simbad.", name)
        raise ValueError(f"Object '{name}' not found in SIMBAD.")

    logger.debug("Successfully resolved '%s'.", name)

    # Check if we got any results
    if len(result) == 0:
        raise ValueError(f"Simbad returned empty result for '{name}'.")

    # Extract RA and Dec from the query result
    ra = result['ra'][0]
    dec = result['dec'][0]
    coord = SkyCoord(ra, dec, unit=(u.hourangle, u.deg), frame='icrs')

    # Only cache successful results — exceptions propagate without poisoning the cache
    with _simbad_cache_lock:
        _simbad_cache[name] = coord

    return coord


def _get_celestial_object(name: str, time: Time) -> SkyCoord:
    """Resolve a celestial object name to its SkyCoord.
    Supports:
    - Solar system objects (sun, moon, planets)
    - Stars (e.g., "sirius")
    - Deep-space objects (e.g., "andromeda", "orion_nebula")
    """
    name = name.lower()

    # Solar system objects
    if name == 'sun':
        return get_sun(time)
    elif name == 'moon':
        return get_body('moon', time)
    elif name in ['mercury', 'venus', 'mars', 'jupiter', 'saturn', 'uranus', 'neptune']:
        return get_body(name, time)

    # Deep-space objects (stars, galaxies, nebulae)
    try:
        return _resolve_simbad_object(name)

    except Exception as e:
        raise ValueError(f"Failed to resolve object '{name}': {str(e)}")


def _generate_time_grid(date: datetime, event_scope: str = 'calendar_day') -> Time:
    """Generate a 5-minute event-search grid for the requested time scope."""
    if event_scope == 'next_events':
        start = Time(date)
        end = Time(date + timedelta(hours=48))
    else:
        start = Time(date.replace(hour=0, minute=0, second=0))
        end = Time(date.replace(hour=23, minute=59, second=59))
    intervals = 576 if event_scope == 'next_events' else 288
    return start + np.linspace(0, 1, intervals) * (end - start)


def _find_rise_set_indices(altitudes: np.ndarray, horizon: float) -> tuple[int | None, int | None]:
    """Find indices where altitude crosses the horizon."""
    above = altitudes > horizon
    diff = np.diff(above.astype(int))
    rise_candidates = np.where(diff == 1)[0]
    set_candidates = np.where(diff == -1)[0]
    rise_idx = int(rise_candidates[0]) if len(rise_candidates) > 0 else None
    set_idx = int(set_candidates[0]) if len(set_candidates) > 0 else None
    return rise_idx, set_idx
