"""Transport-free adapter for stargazing-core spatial weather primitives."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from math import isfinite
from typing import Any

from stargazing_core import OmWeatherReader, WeatherModel, WeatherVariable

from src.utils import parse_observation_time

_SPATIAL_GRID_SHAPE = (96, 96)


def _parse_valid_time(value: str) -> datetime:
    """Parse an OM valid-time string into an aware UTC datetime."""

    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _nearest_valid_time_index(valid_times: list[str], requested_time: datetime) -> int:
    """Choose the closest spatial-model valid time to the request."""

    if not valid_times:
        raise ValueError('Spatial weather model returned no valid times.')
    requested_utc = requested_time.astimezone(UTC)
    return min(
        range(len(valid_times)),
        key=lambda index: abs(_parse_valid_time(valid_times[index]) - requested_utc),
    )


def _sample_window(
    grid: Any,
    *,
    north: float,
    south: float,
    east: float,
    west: float,
    locations: list[dict[str, float]],
) -> list[dict[str, float | None]]:
    """Sample a bounded weather grid at candidate locations."""

    height, width = grid.shape
    samples: list[dict[str, float | None]] = []
    for location in locations:
        lat = float(location['lat'])
        lon = float(location['lon'])
        sample: float | None = None
        if south <= lat <= north and west <= lon <= east:
            row_ratio = (north - lat) / max(north - south, 1e-9)
            col_ratio = (lon - west) / max(east - west, 1e-9)
            row = min(height - 1, max(0, round(row_ratio * (height - 1))))
            col = min(width - 1, max(0, round(col_ratio * (width - 1))))
            value = float(grid[row, col])
            if isfinite(value):
                sample = value
        samples.append({'cloud_cover_percent': sample})
    return samples


def _read_spatial_weather(
    *,
    south: float,
    west: float,
    north: float,
    east: float,
    time: str,
    time_zone: str,
    locations: list[dict[str, float]],
) -> dict[str, Any]:
    """Read one regional cloud-cover grid and sample it for candidates."""

    requested_time = parse_observation_time(time, time_zone)
    reader = OmWeatherReader(WeatherModel.DWD_ICON)
    valid_time_index = _nearest_valid_time_index(reader.valid_times, requested_time)
    grid = reader.read_window(
        WeatherVariable.CLOUD_COVER,
        north=north,
        south=south,
        east=east,
        west=west,
        shape=_SPATIAL_GRID_SHAPE,
        valid_time_index=valid_time_index,
    )
    return {
        'model': reader.model.value,
        'variable': WeatherVariable.CLOUD_COVER.value,
        'valid_time': reader.valid_times[valid_time_index],
        'samples': _sample_window(
            grid,
            north=north,
            south=south,
            east=east,
            west=west,
            locations=locations,
        ),
    }


async def fetch_spatial_weather(**kwargs: Any) -> dict[str, Any]:
    """Fetch regional spatial weather without exposing model policy to agents."""

    return await asyncio.to_thread(_read_spatial_weather, **kwargs)
