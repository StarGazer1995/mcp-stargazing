"""Pydantic models for celestial (astronomy) domain data."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CelestialPosition(BaseModel):
    """Altitude and azimuth of a celestial object."""

    altitude: float = Field(description='Altitude above horizon in degrees (0°=horizon, 90°=zenith)')
    azimuth: float = Field(description='Compass direction in degrees (0°=North, 90°=East)')


class RiseSet(BaseModel):
    """Rise and set times of a celestial object."""

    rise_time: str | None = Field(
        default=None, description='Rise time as ISO string (local timezone)'
    )
    set_time: str | None = Field(
        default=None, description='Set time as ISO string (local timezone)'
    )


class MoonInfo(BaseModel):
    """Detailed information about the Moon's phase and position."""

    illumination: float = Field(description='Fraction of the moon illuminated (0.0 to 1.0)')
    phase_name: str = Field(description="Phase description (e.g. 'Waxing Gibbous')")
    age_days: float = Field(description='Approximate age of the moon in days since New Moon')
    elongation: float = Field(description='Angular separation from Sun in degrees')
    earth_distance: float = Field(description='Distance from Earth in km')
    altitude: float | None = Field(default=None, description='Altitude above horizon in degrees (requires lat/lon)')
    azimuth: float | None = Field(default=None, description='Compass direction in degrees (requires lat/lon)')


class VisiblePlanet(CelestialPosition):
    """A planet currently visible above the horizon."""

    name: str = Field(description='Planet name')
    constellation: str | None = Field(default=None, description='Constellation the planet is in')


class ConstellationInfo(CelestialPosition):
    """Position of a constellation's center point."""

    name: str = Field(description='Constellation name')


class DeepSkyObject(CelestialPosition):
    """A deep sky object (Messier/NGC) with viewing score."""

    name: str = Field(description='Object name')
    type: str = Field(description='Object type (galaxy, nebula, cluster, etc.)')
    magnitude: float = Field(description='Apparent magnitude')
    catalog: str = Field(description='Catalog identifier (Messier, NGC, etc.)')
    score: float = Field(description='Viewing score (lower is better)')


class NightlyForecast(BaseModel):
    """Curated list of best objects to view for a given night."""

    moon_phase: MoonInfo = Field(description='Moon phase details')
    planets: list[VisiblePlanet] = Field(default_factory=list, description='Visible planets')
    deep_sky: list[DeepSkyObject] = Field(
        default_factory=list, description='Recommended deep sky objects'
    )
