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


class NightWindow(BaseModel):
    """Civil-dark observing window around a reference time."""

    local_date: str = Field(description='Local calendar date on which the night starts')
    civil_dusk: str = Field(description='Civil dusk timestamp with timezone offset')
    civil_dawn: str = Field(description='Following civil dawn timestamp with timezone offset')
    duration_hours: float = Field(ge=0, description='Civil-dark duration in hours')
    time_zone: str = Field(description='IANA timezone used for the window')


class NightlyForecast(BaseModel):
    """Curated list of best objects to view for a given night."""

    moon_phase: MoonInfo = Field(description='Moon phase details')
    planets: list[VisiblePlanet] = Field(default_factory=list, description='Visible planets')
    deep_sky: list[DeepSkyObject] = Field(
        default_factory=list, description='Recommended deep sky objects'
    )
    night_window: NightWindow = Field(description='Civil-dark window for the requested night')
