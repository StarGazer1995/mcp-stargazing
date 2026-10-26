"""Application-level task lifecycle; not yet a registered MCP interface."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


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
    state: TaskState = TaskState.QUEUED
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
