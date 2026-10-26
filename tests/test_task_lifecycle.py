"""Deterministic lifecycle, retention, race, and restart semantics without sleeps."""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.schemas.tasks import AnalysisTask, TaskFailure, TaskState
from src.services.tasks import AnalysisTaskRegistry, TaskRegistryCode, TaskRegistryError


@pytest.fixture
def clock():
    class Clock:
        value = datetime(2026, 10, 26, tzinfo=UTC)

        def __call__(self):
            return self.value

        def advance(self, seconds):
            self.value += timedelta(seconds=seconds)

    return Clock()


@pytest.fixture
def registry(clock):
    return AnalysisTaskRegistry(now=clock, timeout_seconds=10, retention_seconds=20)


def test_success_and_snapshot_serialization(registry, clock):
    queued = registry.submit('area-key')
    assert queued.state == TaskState.QUEUED
    assert queued.progress == 0
    assert queued.deadline_at == clock.value + timedelta(seconds=10)
    clock.advance(2)
    running = registry.start(queued.task_id)
    assert running.started_at == clock.value
    assert running.progress is None
    assert queued.state == TaskState.QUEUED
    clock.advance(3)
    done = registry.succeed(queued.task_id)
    assert done.state == TaskState.SUCCEEDED
    assert done.progress == 1
    assert done.resource_id == queued.resource_id
    assert done.finished_at == clock.value
    assert done.expires_at == clock.value + timedelta(seconds=20)
    clock.advance(1)
    assert registry.succeed(done.task_id) == done
    assert registry.cancel(done.task_id) == done
    assert AnalysisTask.model_validate_json(done.model_dump_json()) == done
    with pytest.raises(ValidationError):
        done.state = TaskState.RUNNING
    done.__dict__['resource_id'] = 'tampered'
    assert registry.get(done.task_id).resource_id == 'area-key'


def test_default_clock_is_utc_and_query_retries_get_new_identity():
    registry = AnalysisTaskRegistry()
    first = registry.submit('same-query')
    assert first.created_at.tzinfo == UTC
    assert registry.submit('same-query') == first
    registry.start(first.task_id)
    assert registry.submit('same-query').task_id == first.task_id
    registry.succeed(first.task_id)
    retry = registry.submit('same-query')
    assert retry.task_id != first.task_id
    assert retry.resource_id == first.resource_id


def test_failure_is_retained_and_deeply_isolated(registry):
    task = registry.submit('area-key')
    registry.start(task.task_id)
    failure = TaskFailure(code='NETWORK_ERROR', message='Provider unavailable')
    failed = registry.fail(task.task_id, failure)
    assert failed.state == TaskState.FAILED
    assert failed.failure == failure
    assert failed.progress is None
    assert registry.fail(task.task_id, TaskFailure(code='OTHER', message='Retry')) == failed
    failure.__dict__['message'] = 'mutated after publication'
    # The caller's failure object must not mutate retained registry metadata.
    assert registry.get(task.task_id).failure.message == 'Provider unavailable'
    failed.failure.__dict__['code'] = 'tampered'
    assert registry.get(task.task_id).failure.code == 'NETWORK_ERROR'


@pytest.mark.parametrize('started', [False, True])
def test_cancel_is_terminal_and_rejects_late_worker_results(registry, started):
    task = registry.submit('area-key')
    if started:
        registry.start(task.task_id)
    cancelled = registry.cancel(task.task_id)
    assert cancelled.state == TaskState.CANCELLED
    assert registry.cancel(task.task_id) == cancelled
    for finish in [
        registry.start,
        registry.succeed,
        lambda task_id: registry.fail(task_id, TaskFailure(code='X', message='late')),
    ]:
        with pytest.raises(TaskRegistryError) as error:
            finish(task.task_id)
        assert error.value.code == TaskRegistryCode.INVALID_TRANSITION
    assert registry.submit('area-key').task_id != task.task_id


@pytest.mark.parametrize('started', [False, True])
def test_deadline_and_expiry_boundaries(registry, clock, started):
    task = registry.submit('area-key')
    if started:
        registry.start(task.task_id)
    clock.advance(9)
    assert registry.get(task.task_id).state in {TaskState.QUEUED, TaskState.RUNNING}
    clock.advance(1)
    timeout = registry.get(task.task_id)
    assert timeout.state == TaskState.TIMED_OUT
    assert timeout.finished_at == task.deadline_at
    assert timeout.failure.code == 'task_timeout'
    assert registry.cancel(task.task_id) == timeout
    with pytest.raises(TaskRegistryError):
        registry.succeed(task.task_id)
    clock.advance(19)
    assert registry.get(task.task_id).state == TaskState.TIMED_OUT
    clock.advance(1)
    expired = registry.get(task.task_id)
    assert expired.state == TaskState.EXPIRED
    clock.advance(1)
    assert registry.get(task.task_id) == expired


def test_late_poll_expires_from_deadline_and_submit_cleans_active_index(clock):
    registry = AnalysisTaskRegistry(now=clock, timeout_seconds=5, retention_seconds=5)
    first = registry.submit('area-key')
    clock.advance(11)
    assert registry.get(first.task_id).state == TaskState.EXPIRED
    retry = registry.submit('area-key')
    assert retry.task_id != first.task_id
    clock.advance(5)
    # submit also enforces deadlines without a preceding status poll.
    assert registry.submit('area-key').task_id != retry.task_id


def test_capacity_never_evicts_active_or_unexpired_terminal_records(clock):
    registry = AnalysisTaskRegistry(
        now=clock, max_tasks=2, timeout_seconds=10, retention_seconds=20
    )
    first = registry.submit('one')
    second = registry.submit('two')
    assert registry.submit('one') == first
    for complete in [False, True]:
        if complete:
            registry.cancel(first.task_id)
        with pytest.raises(TaskRegistryError) as error:
            registry.submit('three')
        assert error.value.code == TaskRegistryCode.CAPACITY_EXCEEDED
    clock.advance(20)
    third = registry.submit('three')
    assert third.resource_id == 'three'
    assert registry.get(second.task_id).state == TaskState.TIMED_OUT
    with pytest.raises(TaskRegistryError) as error:
        registry.get(first.task_id)
    assert error.value.code == TaskRegistryCode.UNKNOWN_TASK


def test_lookup_distinguishes_bad_unknown_and_previous_runtime_ids(registry):
    known = registry.submit('query')
    cases = [
        ('not-a-task', TaskRegistryCode.INVALID_TASK_ID),
        (known.task_id.split(':')[0] + ':' + uuid4().hex, TaskRegistryCode.UNKNOWN_TASK),
    ]
    for task_id, expected in cases:
        with pytest.raises(TaskRegistryError) as error:
            registry.get(task_id)
        assert error.value.code == expected
    restarted = AnalysisTaskRegistry()
    with pytest.raises(TaskRegistryError) as error:
        restarted.get(known.task_id)
    assert error.value.code == TaskRegistryCode.RUNTIME_CHANGED
    assert 'resubmit' in str(error.value)


def test_queued_completion_and_conflicting_terminal_updates_are_rejected(registry):
    task = registry.submit('query')
    with pytest.raises(TaskRegistryError):
        registry.succeed(task.task_id)
    registry.start(task.task_id)
    registry.succeed(task.task_id)
    with pytest.raises(TaskRegistryError):
        registry.fail(task.task_id, TaskFailure(code='X', message='late'))


def test_concurrent_duplicate_submissions_and_worker_claims(registry):
    with ThreadPoolExecutor(max_workers=8) as pool:
        submissions = list(pool.map(lambda _: registry.submit('same-query'), range(32)))
    assert len({task.task_id for task in submissions}) == 1
    task_id = submissions[0].task_id

    def claim(_):
        try:
            return registry.start(task_id).state
        except TaskRegistryError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=8) as pool:
        claims = list(pool.map(claim, range(16)))
    assert claims.count(TaskState.RUNNING) == 1
    assert claims.count(TaskRegistryCode.INVALID_TRANSITION) == 15


def test_cancel_and_complete_race_has_one_terminal_outcome(registry):
    task = registry.submit('query')
    registry.start(task.task_id)
    barrier = threading.Barrier(2)

    def act(operation):
        barrier.wait(timeout=5)
        try:
            return operation(task.task_id).state
        except TaskRegistryError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(act, [registry.cancel, registry.succeed]))
    final = registry.get(task.task_id)
    if final.state == TaskState.CANCELLED:
        assert outcomes == [TaskState.CANCELLED, TaskRegistryCode.INVALID_TRANSITION]
    else:
        assert final.state == TaskState.SUCCEEDED
        assert outcomes == [TaskState.SUCCEEDED, TaskState.SUCCEEDED]


@pytest.mark.parametrize('option', ['timeout_seconds', 'retention_seconds'])
@pytest.mark.parametrize('value', [0, -1, float('nan'), float('inf')])
def test_invalid_timing_configuration(option, value):
    with pytest.raises(ValueError):
        AnalysisTaskRegistry(**{option: value})


@pytest.mark.parametrize('value', [0, -1, 1.5, True])
def test_invalid_capacity(value):
    with pytest.raises(ValueError):
        AnalysisTaskRegistry(max_tasks=value)


@pytest.mark.parametrize('resource_id', ['', '   '])
def test_invalid_resource_identity(registry, resource_id):
    with pytest.raises(ValueError):
        registry.submit(resource_id)
