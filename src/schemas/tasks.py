"""Background area-analysis requests and task-status snapshots."""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.schemas.base import GeoBounds


class AreaAnalysisRequest(BaseModel):
    """Business parameters only; task budgets and data sources are server policy."""

    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)

    bounds: GeoBounds = Field(description='Ordered geographic search bounds')
    max_locations: int = Field(
        default=30, ge=1, le=100, description='Place budget before pagination'
    )
    min_height_diff: float = Field(default=100.0, ge=0, description='Minimum elevation difference')
    road_radius_km: float = Field(
        default=10.0, ge=0, description='Road search radius; 0 skips roads'
    )
    network_type: Literal['drive', 'walk', 'bike', 'all'] = Field(
        default='drive', description='Road network mode'
    )
    avoid_popular_spots: bool = Field(default=False, description='Prefer lower popularity risk')
    prefer_quiet_at_night: bool = Field(default=False, description='Prefer night-time quietness')
    popularity_radius_km: float = Field(
        default=3.0, gt=0, description='Popularity preference horizon'
    )

    @model_validator(mode='after')
    def ordered_bounds(self):
        if self.bounds.south >= self.bounds.north or self.bounds.west >= self.bounds.east:
            raise ValueError('bounds must have south < north and west < east.')
        return self

    def search_parameters(self) -> dict:
        return {
            **self.bounds.model_dump(),
            **self.model_dump(exclude={'bounds'}),
            'db_config_path': None,
        }


class TaskState(StrEnum):
    QUEUED = 'queued'
    RUNNING = 'running'
    SUCCEEDED = 'succeeded'
    FAILED = 'failed'
    CANCELLED = 'cancelled'
    TIMED_OUT = 'timed_out'
    EXPIRED = 'expired'


class TaskFailure(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    message: str


class AnalysisTask(BaseModel):
    """Immutable status snapshot, separate from the cached area result payload."""

    model_config = ConfigDict(frozen=True)

    task_id: str
    resource_id: str = Field(description='Existing non-pagination area query identity')
    request: AreaAnalysisRequest | None = Field(
        default=None, description='Normalized business request for resubmission after runtime loss'
    )
    state: TaskState = TaskState.QUEUED
    execution_pending: bool | None = Field(
        default=None,
        description='Whether an executor slot is still reserved, even after cancellation',
    )
    result_revision: str | None = Field(
        default=None,
        description='Cache publication identity; result retrieval verifies this version',
    )
    created_at: datetime
    updated_at: datetime
    deadline_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    expires_at: datetime | None = None
    progress: float | None = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description='0 when queued, unknown while running, 1 only after successful publication',
    )
    failure: TaskFailure | None = None
