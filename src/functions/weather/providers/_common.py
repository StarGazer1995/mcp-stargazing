"""Shared utility functions for weather providers.

Previously these helpers were copy-pasted across open_meteo.py, qweather.py,
and wttr.py.  Extracting them here eliminates ~60% of the boilerplate.
"""

from typing import Any


def to_float(value: str | int | float | None, default: float | None = None) -> float | None:
    """Safely cast a weather data point to float, returning *default* on failure."""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_index(values: list | None, index: int) -> Any:
    """Return ``values[index]`` or None if out of bounds."""
    if values is None or index < 0 or index >= len(values):
        return None
    return values[index]


def percent_index_to_ratio(values: list | None, index: int) -> float | None:
    """Read ``values[index]`` and convert from percent (0–100) to ratio (0.0–1.0)."""
    v = safe_index(values, index)
    if v is None:
        return None
    try:
        return float(v) / 100.0
    except (ValueError, TypeError):
        return None


def to_ratio(value: str | int | float | None) -> float | None:
    """Convert a single percent value (0–100) to a ratio (0.0–1.0)."""
    numeric = to_float(value)
    if numeric is None:
        return None
    return numeric / 100.0


def meters_to_km(value: int | float | None) -> float | None:
    """Convert metres to kilometres, returning None when input is None."""
    if value is None:
        return None
    return float(value) / 1000.0
