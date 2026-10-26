"""Background execution budgets, publication guards, and result retention."""

import threading
from concurrent.futures import CancelledError, ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from src.analysis_cache import AnalysisCache, generate_cache_key
from src.response import MCPError
from src.schemas.places import StargazingLocation
from src.schemas.tasks import AreaAnalysisRequest, TaskState
from src.services.area_tasks import AreaTaskService
from src.services.tasks import AnalysisTaskRegistry


def request(offset=0):
    return AreaAnalysisRequest(
        bounds={
            'south': 30.0 + offset,
            'north': 31.0 + offset,
            'west': 119.0,
            'east': 120.0,
        }
    )


def locations():
    return [
        StargazingLocation(
            name='Dark Ridge',
            lat=30.5,
            lon=119.5,
            score=80,
            bortle_class=3,
            elevation_m=800,
            road_distance_km=0.1,
        )
    ]


@pytest.fixture
def runtime():
    services = []
    gates = []
    now = [datetime(2026, 10, 26, tzinfo=UTC)]

    def event():
        gate = threading.Event()
        gates.append(gate)
        return gate

    def make(compute, *, cache=None, max_workers=1, queue_capacity=1, max_tasks=128):
        registry = AnalysisTaskRegistry(
            now=lambda: now[0],
            timeout_seconds=5,
            retention_seconds=5,
            max_tasks=max_tasks,
        )
        service = AreaTaskService(
            compute,
            cache if cache is not None else AnalysisCache(),
            registry,
            max_workers=max_workers,
            queue_capacity=queue_capacity,
        )
        services.append(service)
        condition = threading.Condition()
        released = set()
        original_release = service._release

        def release(task_id, resource_id):
            original_release(task_id, resource_id)
            with condition:
                released.add(task_id)
                condition.notify_all()

        service._release = release

        def drain(task_id):
            with condition:
                assert condition.wait_for(lambda: task_id in released, timeout=5)

        return service, drain

    yield make, event, now
    for gate in gates:
        gate.set()
    for service in services:
        with service._lock:
            pending = list(service._jobs.values())
        service.close()
        for future in pending:
            try:
                future.result(timeout=5)
            except CancelledError:
                pass


def test_cancelled_execution_keeps_budget_and_discards_late_result(runtime):
    make, event, _now = runtime
    started, finish = event(), event()

    def compute(_query):
        started.set()
        assert finish.wait(timeout=5)
        return locations()

    service, drain = make(compute, queue_capacity=0)
    task = service.submit(request())
    assert started.wait(timeout=3)
    running = service.status(task.task_id)
    assert running.state == TaskState.RUNNING
    assert running.progress is None
    assert running.execution_pending is True
    assert service.submit(request()).task_id == task.task_id
    with pytest.raises(MCPError) as error:
        service.result(task.task_id)
    assert error.value.code == MCPError.TASK_NOT_READY
    cancelled = service.cancel(task.task_id)
    assert cancelled.state == TaskState.CANCELLED
    assert cancelled.execution_pending is True
    for query, reason in [(request(), 'execution_draining'), (request(1), 'execution_capacity')]:
        with pytest.raises(MCPError) as error:
            service.submit(query)
        assert error.value.code == MCPError.TASK_CAPACITY_EXCEEDED
        assert error.value.details['reason'] == reason
    finish.set()
    drain(task.task_id)
    assert service.status(task.task_id).execution_pending is False
    assert service._cache.get(task.resource_id) is None
    retry = service.submit(request())
    drain(retry.task_id)
    assert retry.task_id != task.task_id
    assert service.result(retry.task_id)[1] == locations()


def test_queued_cancel_prevents_provider_call(runtime):
    make, event, _now = runtime
    started, finish = event(), event()
    calls = []

    def compute(query):
        calls.append(query['south'])
        started.set()
        assert finish.wait(timeout=5)
        return locations()

    service, drain = make(compute)
    first = service.submit(request())
    assert started.wait(timeout=3)
    queued = service.submit(request(1))
    assert queued.state == TaskState.QUEUED
    assert queued.progress == 0
    cancelled = service.cancel(queued.task_id)
    drain(queued.task_id)
    assert cancelled.execution_pending is False
    finish.set()
    drain(first.task_id)
    assert calls == [30.0]
    assert service.status(first.task_id).state == TaskState.SUCCEEDED


def test_queued_deadline_prevents_provider_call(runtime):
    make, event, now = runtime
    started, finish = event(), event()
    compute = MagicMock()

    def blocked(_query):
        started.set()
        assert finish.wait(timeout=5)
        return locations()

    compute.side_effect = blocked
    service, drain = make(compute)
    first = service.submit(request())
    assert started.wait(timeout=3)
    queued = service.submit(request(1))
    now[0] += timedelta(seconds=5)
    assert service.status(queued.task_id).state == TaskState.TIMED_OUT
    finish.set()
    drain(first.task_id)
    drain(queued.task_id)
    assert compute.call_count == 1
    assert service._cache.get(first.resource_id) is None
    assert service._cache.get(queued.resource_id) is None


def test_expired_evicted_job_still_reserves_physical_work(runtime):
    make, event, now = runtime
    started, finish = event(), event()

    def compute(_query):
        started.set()
        assert finish.wait(timeout=5)
        return locations()

    service, drain = make(compute, max_tasks=1)
    first = service.submit(request())
    assert started.wait(timeout=3)
    now[0] += timedelta(seconds=10)
    assert service.status(first.task_id).state == TaskState.EXPIRED
    with pytest.raises(MCPError) as error:
        service.result(first.task_id)
    assert error.value.code == MCPError.TASK_RESULT_EXPIRED
    second = service.submit(request(1))  # Evicts only the expired metadata.
    with pytest.raises(MCPError) as error:
        service.submit(request())
    assert error.value.details['reason'] == 'execution_draining'
    service.close()  # Also handles a running job whose metadata was evicted.
    finish.set()
    drain(first.task_id)
    drain(second.task_id)
    assert service._cache.get(first.resource_id) is None
    assert service._cache.get(second.resource_id) is None


def test_cache_hit_empty_result_and_independent_result_expiry(runtime):
    make, _event, _now = runtime
    cache = AnalysisCache()
    query = request()
    resource_id = generate_cache_key(**query.search_parameters())
    cache.set(resource_id, [])
    compute = MagicMock()
    service, _drain = make(compute, cache=cache)
    task = service.submit(query)
    assert task.state == TaskState.SUCCEEDED
    assert task.progress == 1
    assert task.execution_pending is False
    assert task.request == query
    assert service.result(task.task_id)[1] == []
    compute.assert_not_called()
    query.bounds.south = 0
    assert service.status(task.task_id).request.bounds.south == 30.0
    cache.ttl = 0
    with pytest.raises(MCPError) as error:
        service.result(task.task_id)
    assert error.value.code == MCPError.TASK_RESULT_EXPIRED
    assert service.status(task.task_id).state == TaskState.SUCCEEDED


def test_replaced_cache_publication_cannot_be_read_as_an_old_task_result(runtime):
    make, _event, _now = runtime
    cache = AnalysisCache()
    query = request()
    resource_id = generate_cache_key(**query.search_parameters())
    first_revision = cache.set(resource_id, locations())
    service, _drain = make(MagicMock(), cache=cache)
    old = service.submit(query)
    assert old.result_revision == first_revision
    new_revision = cache.set(resource_id, [])
    assert new_revision != first_revision
    with pytest.raises(MCPError) as error:
        service.result(old.task_id)
    assert error.value.code == MCPError.TASK_RESULT_EXPIRED
    retry = service.submit(query)
    assert retry.task_id != old.task_id
    assert retry.resource_id == old.resource_id
    assert retry.result_revision == new_revision
    assert service.result(retry.task_id)[1] == []


@pytest.mark.parametrize(
    'failure',
    [
        MCPError(MCPError.NETWORK_ERROR, 'internal provider path'),
        RuntimeError('/private/secret'),
    ],
)
def test_failed_execution_is_reported_without_leaking_internal_details(runtime, failure):
    make, _event, now = runtime
    service, drain = make(MagicMock(side_effect=failure))
    task = service.submit(request())
    drain(task.task_id)
    failed = service.status(task.task_id)
    assert failed.state == TaskState.FAILED
    assert failed.execution_pending is False
    assert failed.failure.code == (
        MCPError.NETWORK_ERROR if isinstance(failure, MCPError) else MCPError.EXTERNAL_API_ERROR
    )
    assert str(failure) not in failed.failure.message
    with pytest.raises(MCPError) as error:
        service.result(task.task_id)
    assert error.value.code == MCPError.TASK_UNAVAILABLE
    now[0] += timedelta(seconds=5)
    assert service.status(task.task_id).state == TaskState.EXPIRED


def test_late_failure_after_shutdown_preserves_cancellation(runtime):
    make, event, _now = runtime
    started, finish = event(), event()

    def compute(_query):
        started.set()
        assert finish.wait(timeout=5)
        raise RuntimeError('late failure')

    service, drain = make(compute)
    task = service.submit(request())
    assert started.wait(timeout=3)
    service.close()
    assert service.status(task.task_id).state == TaskState.CANCELLED
    with pytest.raises(MCPError) as error:
        service.submit(request(1))
    assert error.value.code == MCPError.CONFIGURATION_ERROR
    finish.set()
    drain(task.task_id)
    assert service.status(task.task_id).state == TaskState.CANCELLED
    assert service.status(task.task_id).failure is None


def test_executor_submission_failure_cleans_logical_task(runtime, monkeypatch):
    make, _event, _now = runtime
    service, _drain = make(lambda _: locations())
    monkeypatch.setattr(service._executor, 'submit', MagicMock(side_effect=RuntimeError('closed')))
    with pytest.raises(MCPError) as error:
        service.submit(request())
    assert error.value.code == MCPError.CONFIGURATION_ERROR
    assert not service._jobs
    assert not service._resources
    assert next(iter(service.registry._records.values())).state == TaskState.CANCELLED


def test_result_publication_and_success_are_atomic_against_cancel():
    registry = AnalysisTaskRegistry()
    task = registry.submit('query')
    registry.start(task.task_id)
    entered, release = threading.Event(), threading.Event()
    published = []

    def publish():
        entered.set()
        assert release.wait(timeout=5)
        published.append('result')

    with ThreadPoolExecutor(max_workers=2) as pool:
        complete = pool.submit(registry.succeed, task.task_id, publish)
        assert entered.wait(timeout=3)
        cancel = pool.submit(registry.cancel, task.task_id)
        release.set()
        assert complete.result(timeout=3).state == TaskState.SUCCEEDED
        assert cancel.result(timeout=3).state == TaskState.SUCCEEDED
    registry.succeed(task.task_id, publish)
    assert published == ['result']


@pytest.mark.parametrize(
    'options',
    [
        {'max_workers': 0},
        {'max_workers': True},
        {'max_workers': 1.5},
        {'queue_capacity': -1},
        {'queue_capacity': True},
        {'queue_capacity': 1.5},
    ],
)
def test_invalid_execution_budget(options):
    with pytest.raises(ValueError):
        AreaTaskService(lambda _: [], AnalysisCache(), AnalysisTaskRegistry(), **options)
