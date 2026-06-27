"""Pydantic models for places / stargazing location domain."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LightPollutionGridPoint(BaseModel):
    """A single data point in a light pollution grid."""

    lat: float = Field(description='Latitude of the grid point')
    lon: float = Field(description='Longitude of the grid point')
    brightness: float | None = Field(
        default=None, description='Brightness value (nanoWatts/cm²/sr)'
    )
    bortle: int | None = Field(default=None, description='Bortle class (1-9, lower is darker)')
    sqm: float | None = Field(default=None, description='Sky Quality Meter value (mag/arcsec²)')
    intensity: float | None = Field(default=None, description='Normalized intensity (0-1)')
    radiance: float | None = Field(default=None, description='Radiance value (nW/cm²/sr)')
    rgb: list[int] | None = Field(default=None, description='RGB color tuple')
    hex: str | None = Field(default=None, description='Hex color string')
    name: str | None = Field(default=None, description='Point label')
    overlay_name: str | None = Field(default=None, description='Data source overlay name')

    @classmethod
    def from_spf_point(cls, point: dict) -> LightPollutionGridPoint:
        """Build from a stargazingplacefinder raw grid point dict."""
        sqm_raw = point.get('sqm')
        return cls(
            lat=float(point['lat']),
            lon=float(point.get('lng', point.get('lon', 0))),
            brightness=point.get('brightness'),
            bortle=point.get('bortle'),
            sqm=float(sqm_raw) if sqm_raw is not None else None,
            intensity=point.get('intensity'),
            radiance=point.get('radiance'),
            rgb=point.get('rgb'),
            hex=point.get('hex'),
            name=point.get('name'),
            overlay_name=point.get('overlay_name'),
        )


class LightPollutionGrid(BaseModel):
    """Light pollution data for a geographic area."""

    grid: list[LightPollutionGridPoint] = Field(
        default_factory=list, description='Grid data points'
    )
    bounds: dict[str, float] = Field(description='Bounding box: south, west, north, east')
    zoom: int = Field(description='Zoom level used for the grid resolution')


class StargazingLocation(BaseModel):
    """A stargazing location with analysis results."""

    name: str | None = Field(default=None, description='Location name or identifier')
    lat: float = Field(description='Latitude in decimal degrees')
    lon: float = Field(description='Longitude in decimal degrees')
    elevation_m: float | None = Field(default=None, description='Elevation in meters')
    light_pollution_level: str | None = Field(
        default=None, description='Light pollution description'
    )
    bortle_class: int | None = Field(default=None, description='Bortle class (1-9)')
    road_distance_km: float | None = Field(
        default=None, description='Distance to nearest road in km'
    )
    score: float | None = Field(default=None, description='Overall stargazing suitability score')

    @classmethod
    def from_spf_location(cls, loc) -> StargazingLocation:
        """Build from a stargazingplacefinder StargazingLocation object."""
        # spf model uses pydantic — try model_dump() first, fall back to dict access
        if hasattr(loc, 'model_dump'):
            d = loc.model_dump(exclude_none=True)
        elif hasattr(loc, 'dict'):
            d = loc.dict(exclude_none=True)
        else:
            d = dict(loc)
        return cls(
            name=d.get('name'),
            lat=d.get('latitude', d.get('lat')),
            lon=d.get('longitude', d.get('lon')),
            elevation_m=d.get('elevation'),
            light_pollution_level=d.get('light_pollution_level'),
            bortle_class=d.get('light_pollution_bortle'),
            road_distance_km=d.get('distance_to_road_km'),
            score=d.get('stargazing_score'),
        )


class AnalysisAreaResult(BaseModel):
    """Paginated result of stargazing location analysis."""

    items: list[StargazingLocation] = Field(description='Location results for the current page')
    total: int = Field(ge=0, description='Total number of locations found')
    page: int = Field(ge=1, description='Current page number (1-based)')
    page_size: int = Field(ge=1, description='Number of results per page')
    total_pages: int = Field(ge=0, description='Total number of pages')
    resource_id: str = Field(description='Cache key for these search parameters')
