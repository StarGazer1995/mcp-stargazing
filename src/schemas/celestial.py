"""Pydantic models for celestial (astronomy) domain data."""

from __future__ import annotations

from pydantic import BaseModel, Field
from stargazing_core import CelestialPosition, MoonInfo, RiseSet, VisiblePlanet  # noqa: F401


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
    rise_time: float | None = Field(
        default=None,
        description='UTC unix timestamp when the object rises above the horizon',
    )
    set_time: float | None = Field(
        default=None,
        description='UTC unix timestamp when the object sets below the horizon',
    )
    transit_time: float | None = Field(
        default=None, description='UTC unix timestamp of culmination (highest altitude)'
    )
    transit_alt: float | None = Field(
        default=None, description='Altitude in degrees at culmination'
    )
    angular_size_arcmin: float | None = Field(
        default=None, description='Major axis angular size in arcminutes'
    )


class NightlyForecast(BaseModel):
    """Curated list of best objects to view for a given night."""

    moon_phase: MoonInfo = Field(description='Moon phase details')
    planets: list[VisiblePlanet] = Field(default_factory=list, description='Visible planets')
    deep_sky: list[DeepSkyObject] = Field(
        default_factory=list, description='Recommended deep sky objects'
    )
