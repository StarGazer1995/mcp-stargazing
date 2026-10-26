"""Thread-safe, bounded lifecycle registry for future background area analysis.

This module records state only. It does not schedule workers, stop threads,
publish cached results, or expose MCP tools. A worker must publish its result
before acknowledging success, and must handle cancellation/deadline rejection.
"""

import math
import re
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import uuid4

from src.schemas.tasks import AnalysisTask, TaskFailure, TaskState


class TaskRegistryCode(StrEnum):
    INVALID_TASK_ID = 'invalid_task_id'
    UNKNOWN_TASK = 'unknown_task'
    RUNTIME_CHANGED = 'runtime_changed'
    CAPACITY_EXCEEDED = 'capacity_exceeded'
    INVALID_TRANSITION = 'invalid_transition'


class TaskRegistryError(Exception):
    """Internal lifecycle error, distinct from an execution failure."""

    def __init__(self, code: TaskRegistryCode, message: str):
        self.code = code
        super().__init__(message)


_ACTIVE = {TaskState.QUEUED, TaskState.RUNNING}


class AnalysisTaskRegistry:
    """One runtime's task metadata, using an injected UTC clock for deadlines.

    ``resource_id`` must come from the existing area query/cache-key function.
    Duplicate active queries share a task; retries after a terminal outcome get
    a new task. Records expire independently from the area's result cache.
    """

    def __init__(
        self,
        *,
        timeout_seconds: float = 600.0,
        retention_seconds: float = 3600.0,
        max_tasks: int = 128,
        now: Callable[[], datetime] | None = None,
    ):
        for value in (timeout_seconds, retention_seconds):
            if not math.isfinite(value) or value <= 0:
                raise ValueError('Task timeout and retention must be finite and positive.')
        if isinstance(max_tasks, bool) or not isinstance(max_tasks, int) or max_tasks < 1:
            raise ValueError('max_tasks must be a positive integer.')
        self._timeout = timedelta(seconds=timeout_seconds)
        self._retention = timedelta(seconds=retention_seconds)
        self._max_tasks = max_tasks
        self._now = now or (lambda: datetime.now(UTC))
        self._runtime_id = uuid4().hex
        self._records: dict[str, AnalysisTask] = {}
        self._active: dict[str, str] = {}
        self._lock = threading.RLock()

    def _finish(
        self,
        record: AnalysisTask,
        state: TaskState,
        at: datetime,
        failure: TaskFailure | None = None,
    ) -> AnalysisTask:
        updated = record.model_copy(
            update={
                'state': state,
                'updated_at': at,
                'finished_at': at,
                'expires_at': at + self._retention,
                'progress': 1.0 if state == TaskState.SUCCEEDED else record.progress,
                'failure': failure.model_copy(deep=True) if failure is not None else None,
            }
        )
        self._records[record.task_id] = updated
        self._active.pop(record.resource_id, None)
        return updated

    def _refresh(self, record: AnalysisTask, now: datetime) -> AnalysisTask:
        if record.state in _ACTIVE and now >= record.deadline_at:
            record = self._finish(
                record,
                TaskState.TIMED_OUT,
                record.deadline_at,
                TaskFailure(code='task_timeout', message='The task deadline elapsed.'),
            )
        if (
            record.state != TaskState.EXPIRED
            and record.expires_at is not None
            and now >= record.expires_at
        ):
            record = record.model_copy(update={'state': TaskState.EXPIRED, 'updated_at': now})
            self._records[record.task_id] = record
        return record

    def _get(self, task_id: str, now: datetime) -> AnalysisTask:
        if re.fullmatch(r'[0-9a-f]{32}:[0-9a-f]{32}', task_id) is None:
            raise TaskRegistryError(TaskRegistryCode.INVALID_TASK_ID, 'Malformed task identifier.')
        if task_id.split(':', 1)[0] != self._runtime_id:
            raise TaskRegistryError(
                TaskRegistryCode.RUNTIME_CHANGED,
                'This task belongs to another runtime; resubmit the original query.',
            )
        if task_id not in self._records:
            raise TaskRegistryError(TaskRegistryCode.UNKNOWN_TASK, 'Task is unknown or evicted.')
        return self._refresh(self._records[task_id], now)

    def submit(self, resource_id: str) -> AnalysisTask:
        """Atomically reuse active work or allocate one retained task record."""
        if not resource_id or not resource_id.strip():
            raise ValueError('resource_id must be a nonempty area query identity.')
        with self._lock:
            now = self._now()
            for record in list(self._records.values()):
                self._refresh(record, now)
            if resource_id in self._active:
                return self._records[self._active[resource_id]].model_copy(deep=True)
            for task_id, record in list(self._records.items()):
                if len(self._records) < self._max_tasks:
                    break
                if record.state == TaskState.EXPIRED:
                    del self._records[task_id]
            if len(self._records) >= self._max_tasks:
                raise TaskRegistryError(
                    TaskRegistryCode.CAPACITY_EXCEEDED,
                    'Task retention capacity is full; retry after retained records expire.',
                )
            task_id = f'{self._runtime_id}:{uuid4().hex}'
            record = AnalysisTask(
                task_id=task_id,
                resource_id=resource_id,
                created_at=now,
                updated_at=now,
                deadline_at=now + self._timeout,
            )
            self._records[task_id] = record
            self._active[resource_id] = task_id
            return record.model_copy(deep=True)

    def get(self, task_id: str) -> AnalysisTask:
        """Poll metadata without implying that cached result data still exists."""
        with self._lock:
            return self._get(task_id, self._now()).model_copy(deep=True)

    def start(self, task_id: str) -> AnalysisTask:
        """Atomically claim queued work; a second worker cannot claim it again."""
        with self._lock:
            now = self._now()
            record = self._get(task_id, now)
            if record.state != TaskState.QUEUED:
                raise TaskRegistryError(TaskRegistryCode.INVALID_TRANSITION, 'Task cannot start.')
            record = record.model_copy(
                update={
                    'state': TaskState.RUNNING,
                    'started_at': now,
                    'updated_at': now,
                    'progress': None,
                }
            )
            self._records[task_id] = record
            return record.model_copy(deep=True)

    def _complete(
        self,
        task_id: str,
        state: TaskState,
        failure: TaskFailure | None = None,
    ) -> AnalysisTask:
        now = self._now()
        record = self._get(task_id, now)
        if record.state == state:
            return record.model_copy(deep=True)
        if record.state != TaskState.RUNNING:
            raise TaskRegistryError(
                TaskRegistryCode.INVALID_TRANSITION,
                'Only running tasks can acknowledge completion.',
            )
        return self._finish(record, state, now, failure).model_copy(deep=True)

    def succeed(self, task_id: str) -> AnalysisTask:
        """Acknowledge successful result publication; late acknowledgements fail."""
        with self._lock:
            return self._complete(task_id, TaskState.SUCCEEDED)

    def fail(self, task_id: str, failure: TaskFailure) -> AnalysisTask:
        with self._lock:
            return self._complete(task_id, TaskState.FAILED, failure)

    def cancel(self, task_id: str) -> AnalysisTask:
        """Record logical cancellation, idempotently; this does not stop a thread."""
        with self._lock:
            now = self._now()
            record = self._get(task_id, now)
            if record.state not in _ACTIVE:
                return record.model_copy(deep=True)
            return self._finish(record, TaskState.CANCELLED, now).model_copy(deep=True)
