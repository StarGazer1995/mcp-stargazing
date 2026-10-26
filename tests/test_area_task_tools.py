"""Public task envelopes, validation, pagination, SDK calls, and lifecycle cleanup."""

import asyncio
import json
from argparse import Namespace
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastmcp import Client

import src.main  # noqa: F401
from examples import background_area_demo
from src.analysis_cache import AnalysisCache, generate_cache_key
from src.functions.places import impl as places
from src.functions.places import tasks_impl as tools
from src.response import MCPError
from src.schemas import AreaAnalysisRequest, StargazingLocation, TaskFailure, TaskState
from src.server_instance import _server_lifespan, mcp
from src.services.area_tasks import AreaTaskService
from src.services.tasks import AnalysisTaskRegistry


def request():
    return AreaAnalysisRequest(bounds={'south': 30, 'west': 119, 'north': 31, 'east': 120})


def locations():
    return [
        StargazingLocation(
            name='Ridge',
            lat=30.1,
            lon=119.1,
            score=80,
            elevation_m=800,
            bortle_class=3,
            road_distance_km=0.1,
        ),
        StargazingLocation(name='Valley', lat=30.2, lon=119.2, score=75),
    ]


@pytest.fixture
def service(monkeypatch):
    now = [datetime(2026, 10, 26, tzinfo=UTC)]
    cache = AnalysisCache()
    compute = MagicMock(return_value=locations())
    runtime = AreaTaskService(
        compute,
        cache,
        AnalysisTaskRegistry(now=lambda: now[0], retention_seconds=10),
    )
    monkeypatch.setattr(tools, '_runtime', runtime)
    monkeypatch.setattr(places, 'ANALYSIS_CACHE', cache)
    yield runtime, cache, compute, now
    runtime.close()


@pytest.mark.asyncio
async def test_task_fn_round_trip_matches_existing_area_pagination(service):
    runtime, cache, compute, _now = service
    query = request()
    key = generate_cache_key(**query.search_parameters())
    cache.set(key, locations())
    submitted = await tools.submit_area_analysis.fn(query)
    task_id = submitted['data']['task_id']
    assert submitted['_meta']['task_id'] == task_id
    assert submitted['_meta']['progress'] == 1
    assert submitted['data']['request'] == query.model_dump()
    assert 'db_config_path' not in submitted['data']['request']
    assert submitted['data']['execution_pending'] is False
    polled = await tools.get_area_analysis_task.fn(task_id)
    assert polled['data']['state'] == 'succeeded'
    cancelled = await tools.cancel_area_analysis_task.fn(task_id)
    assert cancelled['data']['state'] == 'succeeded'
    first = await tools.get_area_analysis_result.fn(task_id, page=1, page_size=1)
    second = await tools.get_area_analysis_result.fn(task_id, page=2, page_size=1)
    assert first['data']['items'][0]['name'] == 'Ridge'
    assert second['data']['items'][0]['name'] == 'Valley'
    assert first['data']['resource_id'] == second['data']['resource_id'] == key
    assert first['_meta']['warnings']
    legacy = await places.analysis_area.fn(**query.search_parameters(), page=2, page_size=1)
    assert second['data'] == legacy['data']
    assert second['_meta']['warnings'] == legacy['_meta']['warnings']
    outside = await tools.get_area_analysis_result.fn(task_id, page=100, page_size=1)
    assert outside['data']['items'] == []
    assert outside['data']['total'] == 2
    for response in (submitted, polled, cancelled, first, second, outside):
        assert json.loads(json.dumps(response)) == response
    for page, size in [(0, 10), (1, 0)]:
        invalid = await tools.get_area_analysis_result.fn(task_id, page=page, page_size=size)
        assert invalid['error']['code'] == MCPError.CONFIGURATION_ERROR
    cache.ttl = 0
    expired = await tools.get_area_analysis_result.fn(task_id)
    assert expired['error']['code'] == MCPError.TASK_RESULT_EXPIRED
    assert runtime.status(task_id).state == TaskState.SUCCEEDED
    compute.assert_not_called()


@pytest.mark.asyncio
async def test_real_sdk_client_calls_background_tools(service):
    _runtime, _cache, compute, _now = service
    async with Client(mcp._mcp) as client:
        submitted = await client.call_tool(
            'submit_area_analysis', {'request': request().model_dump()}
        )
        payload = submitted.structured_content
        assert payload['_meta']['status'] == 'success'
        task_id = payload['data']['task_id']
        async with asyncio.timeout(5):
            while True:
                result = await client.call_tool('get_area_analysis_task', {'task_id': task_id})
                status = result.structured_content['data']
                if status['state'] not in {'queued', 'running'}:
                    break
                await asyncio.sleep(0.01)
        assert status['state'] == 'succeeded'
        data = await client.call_tool(
            'get_area_analysis_result',
            {
                'task_id': task_id,
                'page': 2,
                'page_size': 1,
            },
        )
        assert data.structured_content['data']['items'][0]['name'] == 'Valley'
        cancelled = await client.call_tool('cancel_area_analysis_task', {'task_id': task_id})
        assert cancelled.structured_content['data']['state'] == 'succeeded'
    compute.assert_called_once_with(request().search_parameters())


@pytest.mark.asyncio
async def test_background_example_submits_pages_resumes_and_cancels(service, monkeypatch):
    _runtime, cache, compute, _now = service
    query = AreaAnalysisRequest(bounds=request().bounds, max_locations=10, road_radius_km=0)
    cache.set(generate_cache_key(**query.search_parameters()), locations())
    args = Namespace(
        url=mcp._mcp,
        task_id=None,
        cancel=False,
        south=30,
        west=119,
        north=31,
        east=120,
        max_locations=10,
        wait_seconds=5,
        page=2,
        page_size=1,
    )
    output = []
    monkeypatch.setattr(
        background_area_demo, 'print', lambda value, **_: output.append(value), raising=False
    )
    # Keep one server lifespan across successive client connections.
    async with mcp._mcp._lifespan_manager():
        await background_area_demo.run(args)
        args.task_id = output[0].removeprefix('Task: ')
        assert json.loads(output[-1])['items'][0]['name'] == 'Valley'
        args.page = 1
        await background_area_demo.run(args)
        assert json.loads(output[-1])['items'][0]['name'] == 'Ridge'
        args.cancel = True
        await background_area_demo.run(args)
        assert json.loads(output[-1])['state'] == 'succeeded'
    compute.assert_not_called()


@pytest.mark.asyncio
async def test_task_execution_failure_is_data_while_result_access_is_an_error(service):
    runtime, _cache, _compute, now = service
    task = runtime.registry.submit('failed', request())
    runtime.registry.start(task.task_id)
    runtime.registry.fail(
        task.task_id, TaskFailure(code=MCPError.NETWORK_ERROR, message='Unavailable')
    )
    response = await tools.get_area_analysis_task.fn(task.task_id)
    assert response['_meta']['status'] == 'success'
    assert 'progress' not in response['_meta']
    assert response['data']['state'] == 'failed'
    assert response['data']['failure']['code'] == MCPError.NETWORK_ERROR
    missing = await tools.get_area_analysis_result.fn(task.task_id)
    assert missing['_meta']['status'] == 'error'
    assert missing['error']['code'] == MCPError.TASK_UNAVAILABLE
    now[0] += timedelta(seconds=10)
    expired = await tools.get_area_analysis_result.fn(task.task_id)
    assert expired['error']['code'] == MCPError.TASK_RESULT_EXPIRED


@pytest.mark.asyncio
async def test_task_control_errors_remain_structured(service):
    runtime, _cache, _compute, _now = service
    task = runtime.registry.submit('queued')
    ids = [
        ('bad-id', MCPError.CONFIGURATION_ERROR),
        (task.task_id.split(':')[0] + ':' + uuid4().hex, MCPError.TASK_NOT_FOUND),
        (AnalysisTaskRegistry().submit('other-runtime').task_id, MCPError.TASK_RUNTIME_CHANGED),
    ]
    for task_id, expected in ids:
        for operation in (
            tools.get_area_analysis_task,
            tools.cancel_area_analysis_task,
            tools.get_area_analysis_result,
        ):
            response = await operation.fn(task_id)
            assert response['error']['code'] == expected
            assert response['_meta']['task_id'] == task_id
            assert json.loads(json.dumps(response)) == response
    pending = await tools.get_area_analysis_result.fn(task.task_id)
    assert pending['error']['code'] == MCPError.TASK_NOT_READY


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'changes,expected',
    [
        ({'max_locations': 0}, MCPError.CONFIGURATION_ERROR),
        ({'road_radius_km': -1}, MCPError.CONFIGURATION_ERROR),
        ({'popularity_radius_km': 0}, MCPError.CONFIGURATION_ERROR),
        ({'network_type': 'fly'}, MCPError.CONFIGURATION_ERROR),
        ({'db_config_path': '/private/secret'}, MCPError.CONFIGURATION_ERROR),
        (
            {'bounds': {'south': 91, 'west': 119, 'north': 92, 'east': 120}},
            MCPError.INVALID_COORDINATES,
        ),
        (
            {'bounds': {'south': 31, 'west': 119, 'north': 30, 'east': 120}},
            MCPError.INVALID_COORDINATES,
        ),
    ],
)
async def test_submit_validation(changes, expected, service):
    response = await tools.submit_area_analysis.fn({**request().model_dump(), **changes})
    assert response['error']['code'] == expected
    assert '/private/secret' not in json.dumps(response)
    service[2].assert_not_called()


@pytest.mark.asyncio
async def test_submit_rechecks_a_mutated_request_model(service):
    query = request()
    query.bounds.south = 32
    response = await tools.submit_area_analysis.fn(query)
    assert response['error']['code'] == MCPError.CONFIGURATION_ERROR
    service[2].assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'name,value',
    [
        ('STARGAZING_TASK_WORKERS', '0'),
        ('STARGAZING_TASK_QUEUE_CAPACITY', '-1'),
        ('STARGAZING_TASK_MAX_RECORDS', '0'),
        ('STARGAZING_TASK_TIMEOUT_SECONDS', 'nan'),
        ('STARGAZING_TASK_RETENTION_SECONDS', 'bad'),
    ],
)
async def test_invalid_server_task_policy(name, value, monkeypatch):
    monkeypatch.setattr(tools, '_runtime', None)
    monkeypatch.setenv(name, value)
    response = await tools.submit_area_analysis.fn(request())
    assert response['error']['code'] == MCPError.CONFIGURATION_ERROR
    assert tools._runtime is None


def test_production_runtime_is_lazy_reused_and_closed(monkeypatch):
    monkeypatch.setattr(tools, '_runtime', None)
    tools.shutdown_area_tasks()
    runtime = tools.get_area_task_service()
    try:
        assert tools.get_area_task_service() is runtime
        tools.shutdown_area_tasks()
        with pytest.raises(MCPError):
            runtime.submit(request())
    finally:
        runtime.close()


@pytest.mark.asyncio
async def test_unexpected_adapter_errors_do_not_leak_internals(service, monkeypatch):
    monkeypatch.setattr(
        service[0], 'status', MagicMock(side_effect=RuntimeError('/private/secret'))
    )
    response = await tools.get_area_analysis_task.fn('id')
    assert response['error']['code'] == MCPError.EXTERNAL_API_ERROR
    assert '/private/secret' not in json.dumps(response)


@pytest.mark.asyncio
async def test_server_lifespan_always_closes_task_runtime(monkeypatch):
    shutdown = MagicMock()
    monkeypatch.setattr(tools, 'shutdown_area_tasks', shutdown)
    async with _server_lifespan(None):
        shutdown.assert_not_called()
    assert shutdown.call_count == 1
    with pytest.raises(RuntimeError):
        async with _server_lifespan(None):
            raise RuntimeError('server failure')
    assert shutdown.call_count == 2


@pytest.mark.asyncio
async def test_result_requires_request_metadata(service):
    runtime, cache, _compute, _now = service
    task = runtime.registry.submit('legacy-task')
    runtime.registry.start(task.task_id)
    runtime.registry.succeed(task.task_id, publish=lambda: cache.set('legacy-task', []))
    response = await tools.get_area_analysis_result.fn(task.task_id)
    assert response['error']['code'] == MCPError.CONFIGURATION_ERROR
