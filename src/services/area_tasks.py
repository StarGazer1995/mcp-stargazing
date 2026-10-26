"""Bounded background area analysis with guarded result publication."""

import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from contextvars import copy_context
from typing import Any

from src.analysis_cache import AnalysisCache, generate_cache_key
from src.logging_config import get_logger
from src.response import MCPError
from src.schemas.places import StargazingLocation
from src.schemas.tasks import AnalysisTask, AreaAnalysisRequest, TaskFailure, TaskState
from src.services.tasks import AnalysisTaskRegistry, TaskRegistryError

logger = get_logger(__name__)
_ACTIVE = {TaskState.QUEUED, TaskState.RUNNING}


class AreaTaskService:
    """A process-local execution budget independent from logical task retention.

    Cancelled/timed-out synchronous calls keep their physical slot and resource
    reservation until their future actually finishes. No worker publishes after
    its task has become terminal through cancellation, timeout, or expiry.
    """

    def __init__(
        self,
        compute: Callable[[dict[str, Any]], list[StargazingLocation]],
        cache: AnalysisCache,
        registry: AnalysisTaskRegistry,
        *,
        max_workers: int = 2,
        queue_capacity: int = 8,
    ):
        for name, value, minimum in (
            ('max_workers', max_workers, 1),
            ('queue_capacity', queue_capacity, 0),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                raise ValueError(f'{name} must be an integer >= {minimum}.')
        self.registry = registry
        self._compute = compute
        self._cache = cache
        self._capacity = max_workers + queue_capacity
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix='area-task')
        self._jobs: dict[str, Future] = {}
        self._resources: dict[str, str] = {}
        self._lock = threading.RLock()
        self._closed = False

    def submit(self, request: AreaAnalysisRequest) -> AnalysisTask:
        query = request.search_parameters()
        resource_id = generate_cache_key(**query)
        with self._lock:
            if self._closed:
                raise MCPError(MCPError.CONFIGURATION_ERROR, 'Background area service is closed.')
            if resource_id in self._resources:
                old_id = self._resources[resource_id]
                try:
                    old = self.registry.get(old_id)
                except TaskRegistryError:
                    old = None
                if old is not None and old.state in _ACTIVE:
                    return self._execution_snapshot(old)
                raise MCPError(
                    MCPError.TASK_CAPACITY_EXCEEDED,
                    'The previous execution is still finishing; retry later.',
                    {'reason': 'execution_draining', 'task_id': old_id},
                )
            cached = self._cache.get_versioned(resource_id)
            if cached is not None:
                task = self.registry.submit(resource_id, request)
                self.registry.start(task.task_id)
                return self._execution_snapshot(
                    self.registry.succeed(task.task_id, publish=lambda: cached[1])
                )
            if len(self._jobs) >= self._capacity:
                raise MCPError(
                    MCPError.TASK_CAPACITY_EXCEEDED,
                    'Background area execution capacity is full; retry later.',
                    {'reason': 'execution_capacity'},
                )
            task = self.registry.submit(resource_id, request)
            try:
                future = self._executor.submit(copy_context().run, self._run, task.task_id, query)
            except RuntimeError as exc:
                self.registry.cancel(task.task_id)
                raise MCPError(
                    MCPError.CONFIGURATION_ERROR, 'Background area executor is unavailable.'
                ) from exc
            self._jobs[task.task_id] = future
            self._resources[resource_id] = task.task_id
            future.add_done_callback(lambda _: self._release(task.task_id, resource_id))
            return self._execution_snapshot(self.registry.get(task.task_id))

    def _release(self, task_id: str, resource_id: str) -> None:
        with self._lock:
            self._jobs.pop(task_id, None)
            if self._resources.get(resource_id) == task_id:
                del self._resources[resource_id]

    def _run(self, task_id: str, query: dict[str, Any]) -> None:
        try:
            self.registry.start(task_id)
        except TaskRegistryError:
            return  # Cancelled or expired before a worker could claim it.
        try:
            locations = self._compute(query)
            self.registry.succeed(
                task_id, publish=lambda: self._cache.set(generate_cache_key(**query), locations)
            )
        except TaskRegistryError:
            return  # Late results are discarded before cache publication.
        except Exception as exc:
            logger.exception('Background area analysis failed')
            code = exc.code if isinstance(exc, MCPError) else MCPError.EXTERNAL_API_ERROR
            try:
                self.registry.fail(
                    task_id,
                    TaskFailure(
                        code=code,
                        message='Area analysis failed; inspect server logs before retrying.',
                    ),
                )
            except TaskRegistryError:
                pass  # A concurrent cancel/timeout retains its original terminal state.

    def _execution_snapshot(self, task: AnalysisTask) -> AnalysisTask:
        return task.model_copy(update={'execution_pending': task.task_id in self._jobs})

    def status(self, task_id: str) -> AnalysisTask:
        with self._lock:
            return self._execution_snapshot(self.registry.get(task_id))

    def cancel(self, task_id: str) -> AnalysisTask:
        with self._lock:
            task = self.registry.cancel(task_id)
            future = self._jobs.get(task_id)
            if future is not None:
                future.cancel()  # A running synchronous call cannot be interrupted.
            return self._execution_snapshot(task)

    def result(self, task_id: str) -> tuple[AnalysisTask, list[StargazingLocation]]:
        task = self.status(task_id)
        if task.state != TaskState.SUCCEEDED:
            if task.state in _ACTIVE:
                code = MCPError.TASK_NOT_READY
                action = 'poll'
            elif task.state == TaskState.EXPIRED:
                code = MCPError.TASK_RESULT_EXPIRED
                action = 'resubmit'
            else:
                code = MCPError.TASK_UNAVAILABLE
                action = 'resubmit_after_execution_finishes'
            raise MCPError(
                code,
                'No completed area result is available for this task.',
                {'state': task.state.value, 'next_action': action},
            )
        cached = self._cache.get_versioned(task.resource_id)
        if cached is None or task.result_revision != cached[1]:
            raise MCPError(
                MCPError.TASK_RESULT_EXPIRED,
                'The area result cache expired or was replaced; resubmit the query.',
                {'resource_id': task.resource_id, 'next_action': 'resubmit'},
            )
        return task, cached[0]

    def close(self) -> None:
        """Reject submissions, cancel queued work, and discard late running results."""
        with self._lock:
            self._closed = True
            for task_id in tuple(self._jobs):
                try:
                    self.cancel(task_id)
                except TaskRegistryError:
                    pass
        self._executor.shutdown(wait=False, cancel_futures=True)
