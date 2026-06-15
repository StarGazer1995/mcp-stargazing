"""Core shared Pydantic models used across all domains."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, field_validator


class GeoPoint(BaseModel):
    """A geographic coordinate point with latitude and longitude."""

    lat: Annotated[
        float,
        Field(ge=-90.0, le=90.0, description='Latitude in decimal degrees'),
    ]
    lon: Annotated[
        float,
        Field(ge=-180.0, le=180.0, description='Longitude in decimal degrees'),
    ]
    elevation_m: float | None = Field(
        default=None, ge=0.0, description='Elevation in meters above sea level'
    )

    @field_validator('lat')
    @classmethod
    def _validate_lat(cls, v: float) -> float:
        if not -90.0 <= v <= 90.0:
            raise ValueError(f'Latitude must be between -90 and 90, got {v}')
        return v

    @field_validator('lon')
    @classmethod
    def _validate_lon(cls, v: float) -> float:
        if not -180.0 <= v <= 180.0:
            raise ValueError(f'Longitude must be between -180 and 180, got {v}')
        return v


class GeoBounds(BaseModel):
    """A bounding box defined by south/west/north/east coordinates."""

    south: Annotated[float, Field(ge=-90.0, le=90.0, description='Southern latitude boundary')]
    west: Annotated[
        float,
        Field(ge=-180.0, le=180.0, description='Western longitude boundary'),
    ]
    north: Annotated[float, Field(ge=-90.0, le=90.0, description='Northern latitude boundary')]
    east: Annotated[
        float,
        Field(ge=-180.0, le=180.0, description='Eastern longitude boundary'),
    ]

    @field_validator('north')
    @classmethod
    def _north_must_be_gte_south(cls, v: float, info) -> float:
        if 'south' in info.data and v < info.data['south']:
            raise ValueError(f'north ({v}) must be >= south ({info.data["south"]})')
        return v

    @field_validator('east')
    @classmethod
    def _east_must_be_gte_west(cls, v: float, info) -> float:
        if 'west' in info.data and v < info.data['west']:
            raise ValueError(f'east ({v}) must be >= west ({info.data["west"]})')
        return v


class TimeInfo(BaseModel):
    """A timezone-aware datetime with its IANA timezone identifier."""

    dt: datetime = Field(description='Timezone-aware datetime object')
    timezone: str = Field(description="IANA timezone identifier (e.g. 'Asia/Shanghai')")

    @field_validator('dt')
    @classmethod
    def _dt_must_be_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError(f'Datetime must be timezone-aware, got naive datetime: {v}')
        return v


class ProviderType(StrEnum):
    """Supported weather provider types."""

    ALL = 'all'
    OPEN_METEO = 'open-meteo'
    QWEATHER = 'qweather'
    WTTR = 'wttr'

    @classmethod
    def from_str(cls, value: str) -> ProviderType:
        """Parse from string, case-insensitive."""
        normalized = value.strip().lower()
        for member in cls:
            if member.value == normalized:
                return member
        raise ValueError(f"Unknown provider: '{value}'. Allowed: {[m.value for m in cls]}")
