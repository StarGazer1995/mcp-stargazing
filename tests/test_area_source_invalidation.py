"""Configuration metadata invalidates reuse and fences stale publications."""

import asyncio
import os
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastmcp import Client

from src.analysis_cache import AnalysisCache
from src.area_source_identity import area_source_identity
from src.functions.places import impl
from src.response import MCPError
from src.schemas.places import StargazingLocation
from src.schemas.tasks import AreaAnalysisRequest, TaskState
from src.server_instance import mcp
from src.services.area_tasks import AreaTaskService
from src.services.tasks import AnalysisTaskRegistry


@pytest.fixture
def configured(tmp_path, monkeypatch):
    path = tmp_path / 'source.toml'
    path.write_text('min_height_difference = 17.0\n')
    monkeypatch.setenv('STARGAZING_CONFIG', str(path))
    monkeypatch.delenv('STARGAZING_DB_CONFIG', raising=False)
    return path


def location():
    return [StargazingLocation(name='Synthetic', lat=30.5, lon=119.5)]


def test_missing_default_and_explicit_binding_metadata_without_content_reads(tmp_path, monkeypatch):
    monkeypatch.delenv('STARGAZING_CONFIG', raising=False)
    monkeypatch.delenv('STARGAZING_DB_CONFIG', raising=False)
    defaults = area_source_identity()
    assert defaults == (None,)
    path = tmp_path / 'config.toml'
    monkeypatch.setenv('STARGAZING_CONFIG', str(path))
    missing = area_source_identity()
    assert missing != defaults
    assert missing == area_source_identity()
    path.write_text('synthetic data, never read by identity helper')
    with patch.object(Path, 'open', side_effect=AssertionError('No content access')):
        present = area_source_identity()
    assert present != missing
    replacement = tmp_path / 'replacement.toml'
    replacement.write_text('same-sized replacement fixture')
    os.replace(replacement, path)
    replaced = area_source_identity()
    assert replaced != present
    monkeypatch.setenv('STARGAZING_DB_CONFIG', str(path))
    assert area_source_identity() == replaced  # DB configuration is explicitly outside this scope.
    path.unlink()
    assert area_source_identity()[-1] == ('missing',)


def test_unchanged_source_reuses_revision_and_changed_source_rejects_old_publication(configured):
    cache = AnalysisCache(source_identity=area_source_identity)
    token = cache.source_token()
    revision = cache.set('query', [], expected_source=token)
    assert cache.get_versioned('query') == ([], revision)
    assert cache.source_token() == token
    configured.write_text('min_height_difference = 29.0\n')
    assert cache.get('query') is None
    assert cache.source_token() != token
    with pytest.raises(MCPError) as error:
        cache.set('query', location(), expected_source=token)
    assert error.value.code == MCPError.CONFIGURATION_ERROR
    assert error.value.details['reason'] == 'source_configuration_changed'
    current = cache.source_token()
    cache.set('query', location(), expected_source=current)
    assert cache.get('query') == location()


def test_unverifiable_identity_clears_results_and_does_not_leak_details(configured):
    cache = AnalysisCache(source_identity=area_source_identity)
    token = cache.source_token()
    cache.set('query', location(), expected_source=token)
    with patch.object(Path, 'stat', side_effect=PermissionError('DO_NOT_LEAK')):
        with pytest.raises(MCPError) as error:
            cache.get('query')
    assert error.value.code == MCPError.CONFIGURATION_ERROR
    assert error.value.details['reason'] == 'source_identity_unavailable'
    assert 'DO_NOT_LEAK' not in str(error.value.to_response())
    assert cache.get('query') is None
    with pytest.raises(MCPError):
        cache.set('query', [], expected_source=token)


@pytest.mark.asyncio
async def test_sdk_warm_cache_refresh_and_mid_compute_change_are_guarded(configured, monkeypatch):
    cache = AnalysisCache(source_identity=area_source_identity)
    monkeypatch.setattr(impl, 'ANALYSIS_CACHE', cache)
    compute = MagicMock(return_value=location())
    monkeypatch.setattr(impl, 'compute_area_locations', compute)
    args = dict(south=30, north=31, west=119, east=120)
    async with Client(mcp._mcp) as client:
        first = (await client.call_tool('analysis_area', args)).structured_content
        configured.write_text('min_height_difference = 29.0\n')
        refreshed = (await client.call_tool('analysis_area', args)).structured_content
        assert first['data']['resource_id'] == refreshed['data']['resource_id']
        assert compute.call_count == 2
        started, finish = threading.Event(), threading.Event()

        def blocked(_query):
            started.set()
            assert finish.wait(5)
            return location()

        compute.side_effect = blocked
        pending = asyncio.create_task(
            client.call_tool('analysis_area', {**args, 'max_locations': 2})
        )
        try:
            assert await asyncio.to_thread(started.wait, 5)
            configured.write_text('min_height_difference = 31.0\n')
        finally:
            finish.set()
        reply = (await pending).structured_content
    assert reply['_meta']['status'] == 'error'
    assert reply['error']['code'] == MCPError.CONFIGURATION_ERROR
    assert reply['error']['details']['reason'] == 'source_configuration_changed'
    assert cache._cache == {}


@pytest.mark.parametrize('terminal', ['source_changed', 'cancelled', 'timed_out'])
def test_background_source_fence_preserves_terminal_state_and_allows_resubmit(configured, terminal):
    from datetime import UTC, datetime, timedelta

    now = [datetime(2026, 11, 3, tzinfo=UTC)]
    registry = AnalysisTaskRegistry(now=lambda: now[0], timeout_seconds=10)
    cache = AnalysisCache(source_identity=area_source_identity)
    started, finish, done = threading.Event(), threading.Event(), threading.Event()

    def compute(_query):
        started.set()
        assert finish.wait(5)
        return location()

    service = AreaTaskService(compute, cache, registry)
    release = service._release

    def completed(t, r):
        release(t, r)
        done.set()

    service._release = completed
    query = AreaAnalysisRequest(bounds={'south': 30, 'north': 31, 'west': 119, 'east': 120})
    try:
        task = service.submit(query)
        assert started.wait(5)
        if terminal == 'cancelled':
            service.cancel(task.task_id)
        elif terminal == 'timed_out':
            now[0] += timedelta(seconds=10)
            assert service.status(task.task_id).state == TaskState.TIMED_OUT
        configured.write_text('min_height_difference = 29.0\n')
        finish.set()
        assert done.wait(5)
        status = service.status(task.task_id)
        expected = {
            'source_changed': TaskState.FAILED,
            'cancelled': TaskState.CANCELLED,
            'timed_out': TaskState.TIMED_OUT,
        }[terminal]
        assert status.state == expected
        if terminal == 'source_changed':
            assert status.failure.code == MCPError.CONFIGURATION_ERROR
        assert cache.get(task.resource_id) is None
        done.clear()
        retry = service.submit(query)
        assert done.wait(5)
        assert retry.task_id != task.task_id
        assert service.result(retry.task_id)[1] == location()
        old = service.submit(query)  # A successful cache-backed task.
        configured.write_text('min_height_difference = 31.0\n')
        with pytest.raises(MCPError) as error:
            service.result(old.task_id)
        assert error.value.code == MCPError.TASK_RESULT_EXPIRED
    finally:
        finish.set()
        service.close()
