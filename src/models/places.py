"""Pydantic models for places / stargazing location domain."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class LightPollutionGridPoint(BaseModel):
    """A single data point in a light pollution grid."""

    lat: float = Field(description="Latitude of the grid point")
    lon: float = Field(description="Longitude of the grid point")
    brightness: Optional[float] = Field(default=None, description="Brightness value (nanoWatts/cm²/sr)")
    bortle: Optional[int] = Field(default=None, description="Bortle class (1-9, lower is darker)")
    sqm: Optional[float] = Field(default=None, description="Sky Quality Meter value (mag/arcsec²)")


class LightPollutionGrid(BaseModel):
    """Light pollution data for a geographic area."""

    grid: List[LightPollutionGridPoint] = Field(default_factory=list, description="Grid data points")
    bounds: Dict[str, float] = Field(description="Bounding box: south, west, north, east")
    zoom: int = Field(description="Zoom level used for the grid resolution")


class StargazingLocation(BaseModel):
    """A stargazing location with analysis results."""

    name: Optional[str] = Field(default=None, description="Location name or identifier")
    lat: float = Field(description="Latitude in decimal degrees")
    lon: float = Field(description="Longitude in decimal degrees")
    elevation_m: Optional[float] = Field(default=None, description="Elevation in meters")
    light_pollution_level: Optional[str] = Field(default=None, description="Light pollution description")
    bortle_class: Optional[int] = Field(default=None, description="Bortle class (1-9)")
    road_distance_km: Optional[float] = Field(default=None, description="Distance to nearest road in km")
    score: Optional[float] = Field(default=None, description="Overall stargazing suitability score")


class AnalysisAreaResult(BaseModel):
    """Paginated result of stargazing location analysis."""

    items: List[StargazingLocation] = Field(description="Location results for the current page")
    total: int = Field(ge=0, description="Total number of locations found")
    page: int = Field(ge=1, description="Current page number (1-based)")
    page_size: int = Field(ge=1, description="Number of results per page")
    total_pages: int = Field(ge=0, description="Total number of pages")
    resource_id: str = Field(description="Cache key for these search parameters")
