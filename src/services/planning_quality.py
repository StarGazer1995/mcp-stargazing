"""Internal deep-sky imaging policy; thresholds are conservative heuristics."""

import asyncio
from datetime import datetime
from functools import lru_cache


@lru_cache(maxsize=256)
def _astronomical_bounds(lat: float, lon: float, reference: str) -> tuple[datetime, datetime]:
    # Reuse the existing solar crossing solver, but never publish its internal
    # NightWindow under the civil-dark field names with a different horizon.
    from src.celestial import calculate_civil_night_window
    from src.utils import create_earth_location

    window = calculate_civil_night_window(
        create_earth_location(lat, lon), datetime.fromisoformat(reference), civil_horizon=-18.0
    )
    return datetime.fromisoformat(window.civil_dusk), datetime.fromisoformat(window.civil_dawn)


async def fetch_imaging_bounds(lat: float, lon: float, reference: datetime):
    return await asyncio.to_thread(_astronomical_bounds, lat, lon, reference.isoformat())


# Version these heuristics explicitly so evaluation results remain interpretable.
IMAGING_POLICY = {
    'version': 'deep-sky-v1',
    'max_cloud_percent': 25.0,
    'max_precipitation_probability': 0.20,
    'max_wind_kph': 20.0,
    'minimum_hours': 2.0,
    'solar_horizon_degrees': -18.0,
}
