"""Optional atmospheric states within the aggregated weather contract."""

from typing import Literal

from pydantic import BaseModel, Field


class AtmosphericState(BaseModel):
    """One model-valid hour, with its own time and per-field provenance."""

    time: str = Field(description='Atmospheric valid time, ISO 8601 with explicit UTC offset')
    data_kind: Literal['model_estimate'] = 'model_estimate'
    temporal_role: Literal['past_model_estimate', 'current_model_estimate', 'forecast']
    boundary_layer_height_m: float | None = None
    visibility_km: float | None = None
    pm2_5_ug_m3: float | None = None
    pm10_ug_m3: float | None = None
    no2_ug_m3: float | None = None
    o3_ug_m3: float | None = None
    so2_ug_m3: float | None = None
    co_ug_m3: float | None = None
    aod_550nm: float | None = Field(default=None, description='Dimensionless column extinction')
    dust_ug_m3: float | None = None
    field_sources: dict[str, str] = Field(
        default_factory=dict, description='Non-null field to atmosphere_sources key'
    )


class AtmosphericSource(BaseModel):
    """Dataset provenance and degradation, independent of the weather provider status."""

    status: Literal['success', 'partial', 'error']
    provider: str = 'open-meteo'
    dataset: str
    data_kind: Literal['model_estimate'] = 'model_estimate'
    retrieved_at: str = Field(description='Retrieval-start time; not model run or observation time')
    model_run_time: str | None = None
    documentation_url: str
    attribution: str
    spatial_resolution: str
    native_time_resolution: str
    grid_lat: float | None = None
    grid_lon: float | None = None
    grid_elevation_m: float | None = None
    coverage_start_time: str | None = None
    coverage_end_time: str | None = None
    units: dict[str, str]
    warnings: list[str] = Field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None
