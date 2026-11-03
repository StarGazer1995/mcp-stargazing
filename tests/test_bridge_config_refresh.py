"""Actual recomputations must not keep a stale SPF configuration indefinitely."""

import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastmcp import Client

import src.placefinder as bridge
from src.analysis_cache import AnalysisCache
from src.functions.places import impl
from src.placefinder import StargazingPlaceFinder
from src.schemas.tasks import AreaAnalysisRequest
from src.server_instance import mcp
from src.services.area_tasks import AreaTaskService
from src.services.tasks import AnalysisTaskRegistry


@pytest.fixture
def configured_provider(tmp_path, monkeypatch):
    config_path = tmp_path / 'synthetic.toml'
    config_path.write_text('min_height_difference = 17.0\n')
    monkeypatch.setenv('STARGAZING_CONFIG', str(config_path))
    monkeypatch.delenv('STARGAZING_DB_CONFIG', raising=False)
    monkeypatch.setattr(bridge, '_last_params', None)
    state = {}

    def initialize(**kwargs):
        config = kwargs['config']
        state['value'] = (
            config.min_height_difference if config is not None else kwargs['min_height_difference']
        )

    def analyze(**_kwargs):
        return [
            {
                'name': 'Synthetic configuration echo',
                'latitude': 30.5,
                'longitude': 119.5,
                'stargazing_score': state['value'],
            }
        ]

    provider = SimpleNamespace(
        init_stargazing_analyzer=MagicMock(side_effect=initialize),
        analyze_area=MagicMock(side_effect=analyze),
    )
    monkeypatch.setattr(bridge, '_load_spf', lambda: provider)
    return config_path, provider


def test_real_compute_reloads_changed_toml_with_same_request(configured_provider):
    path, provider = configured_provider
    query = AreaAnalysisRequest(
        bounds={'south': 30, 'north': 31, 'west': 119, 'east': 120},
        road_radius_km=10,
    ).search_parameters()
    first = impl.compute_area_locations(query)
    path.write_text('min_height_difference = 29.0\n')
    second = impl.compute_area_locations(query)
    assert [first[0].score, second[0].score] == [17, 29]
    assert provider.init_stargazing_analyzer.call_count == 2


@pytest.mark.parametrize('change', ['same_file', 'environment_binding'])
def test_reused_bridge_reloads_effective_config(configured_provider, monkeypatch, change):
    path, provider = configured_provider
    finder = StargazingPlaceFinder()
    assert finder.analyze_area(30, 119, 31, 120)[0]['stargazing_score'] == 17
    if change == 'environment_binding':
        path = path.with_name('second.toml')
        monkeypatch.setenv('STARGAZING_CONFIG', str(path))
    path.write_text('min_height_difference = 29.0\n')
    assert finder.analyze_area(30, 119, 31, 120)[0]['stargazing_score'] == 29
    assert provider.init_stargazing_analyzer.call_count == 2


def test_equal_loaded_configs_reuse_resources(configured_provider):
    path, provider = configured_provider
    finder = StargazingPlaceFinder()
    finder.analyze_area(30, 119, 31, 120)
    # File identity/format changes alone do not change the effective model.
    path.write_text('# Same effective values\nmin_height_difference = 17\n')
    another = StargazingPlaceFinder()
    another.analyze_area(30, 119, 31, 120)
    assert provider.init_stargazing_analyzer.call_count == 1


def test_interleaved_bridge_instances_restore_their_own_parameters(
    configured_provider, monkeypatch
):
    _path, provider = configured_provider
    monkeypatch.setattr(bridge, '_load_spf_config', lambda: None)
    first = StargazingPlaceFinder(min_height_difference=20)
    StargazingPlaceFinder(min_height_difference=40)
    assert first.analyze_area(30, 119, 31, 120, min_height_diff=20)[0]['stargazing_score'] == 20
    assert provider.init_stargazing_analyzer.call_count == 3


@pytest.mark.parametrize(
    'failure', [FileNotFoundError('synthetic absent'), RuntimeError('synthetic')]
)
def test_loader_failure_preserves_existing_fallback_then_recovers(
    configured_provider, monkeypatch, failure
):
    _path, provider = configured_provider
    original = bridge._load_spf_config
    monkeypatch.setattr(bridge, '_load_spf_config', MagicMock(side_effect=failure))
    finder = StargazingPlaceFinder()
    assert provider.init_stargazing_analyzer.call_args.kwargs['config'] is None
    monkeypatch.setattr(bridge, '_load_spf_config', original)
    assert finder.analyze_area(30, 119, 31, 120)[0]['stargazing_score'] == 17


@pytest.mark.asyncio
async def test_sdk_cache_hit_retains_policy_but_actual_recompute_uses_new_config(
    configured_provider, monkeypatch
):
    path, provider = configured_provider
    cache = AnalysisCache()
    monkeypatch.setattr(impl, 'ANALYSIS_CACHE', cache)
    parameters = dict(south=30, north=31, west=119, east=120, road_radius_km=10)
    async with Client(mcp._mcp) as client:
        first = (await client.call_tool('analysis_area', parameters)).structured_content['data']
        path.write_text('min_height_difference = 29.0\n')
        cached = (await client.call_tool('analysis_area', parameters)).structured_content['data']
        assert first == cached
        assert provider.init_stargazing_analyzer.call_count == 1
        cache.ttl = 0  # Exercise the unchanged real cache-miss/recompute path.
        updated = (await client.call_tool('analysis_area', parameters)).structured_content['data']
    assert first['resource_id'] == updated['resource_id']
    assert [first['items'][0]['score'], updated['items'][0]['score']] == [17, 29]
    assert provider.init_stargazing_analyzer.call_count == 2


def test_background_actual_computation_uses_current_effective_config(configured_provider):
    path, _provider = configured_provider
    service = AreaTaskService(impl.compute_area_locations, AnalysisCache(), AnalysisTaskRegistry())
    done = threading.Event()
    release = service._release

    def completed(task_id, resource_id):
        release(task_id, resource_id)
        done.set()

    service._release = completed
    first_request = AreaAnalysisRequest(
        bounds={'south': 30, 'north': 31, 'west': 119, 'east': 120},
        road_radius_km=10,
        max_locations=1,
    )
    try:
        first = service.submit(first_request)
        assert done.wait(5)
        assert service.result(first.task_id)[1][0].score == 17
        path.write_text('min_height_difference = 29.0\n')
        done.clear()
        # A distinct query triggers actual computation without claiming source
        # changes invalidate existing cached results or old successful tasks.
        second = service.submit(first_request.model_copy(update={'max_locations': 2}))
        assert done.wait(5)
        assert service.result(second.task_id)[1][0].score == 29
        assert service.result(first.task_id)[1][0].score == 17
    finally:
        service.close()
