"""Atmospheric descriptions must not fabricate coverage or change observing decisions."""

import json
from copy import deepcopy
from dataclasses import replace
from datetime import datetime

import pytest

from evaluations.imaging_quality import build_case
from src.schemas.atmosphere import AtmosphericSource
from src.schemas.planning import ObservationWindow
from src.services.planning import PlanningService
from src.services.planning_atmosphere import FIELD_UNITS, summarize_window_atmosphere


@pytest.fixture
def sources():
    return {
        'model': AtmosphericSource(
            status='success',
            dataset='Test model',
            retrieved_at='2026-11-01T00:00:00Z',
            documentation_url='https://example.com/model',
            attribution='Synthetic test fixture',
            spatial_resolution='test grid',
            native_time_resolution='hourly',
            coverage_start_time='2026-11-08T00:00:00Z',
            coverage_end_time='2026-11-09T00:00:00Z',
            units=FIELD_UNITS,
        ).model_dump(mode='json')
    }


def hour(stamp, value=1):
    return {
        'time': stamp,
        'atmosphere': {
            'time': stamp,
            'data_kind': 'model_estimate',
            'temporal_role': 'forecast',
            'field_sources': {field: 'model' for field in FIELD_UNITS},
            **{field: value for field in FIELD_UNITS},
        },
    }


@pytest.fixture
def window():
    return ObservationWindow(
        start_time='2026-11-08T19:00:00+08:00', end_time='2026-11-08T21:00:00+08:00'
    )


def test_only_selected_window_is_aggregated_and_provenance_survives(sources, window):
    records = [
        hour('2026-11-08T18:00:00+08:00', 100),
        hour('2026-11-08T19:00:00+08:00', 0),
        hour('2026-11-08T20:00:00+08:00', 2),
        hour('2026-11-08T21:00:00+08:00', 100),
    ]
    result = summarize_window_atmosphere(records, sources, window)
    assert result['status'] == 'available'
    assert result['expected_samples'] == 2
    aod = result['fields']['aod_550nm']
    assert (aod['minimum'], aod['maximum'], aod['mean']) == (0, 2, 1)
    assert aod['valid_samples'] == 2 and aod['missing_samples'] == 0
    assert aod['sources'] == ['model']
    assert result['sources']['model']['retrieved_at'] == '2026-11-01T00:00:00Z'
    assert result['sources']['model']['model_run_time'] is None
    assert result['temporal_roles'] == ['forecast']
    assert result['affects_ranking'] is False
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize('value', [None, True, -1, float('nan'), float('inf'), 10**1000])
def test_invalid_values_and_partial_coverage_are_not_imputed(sources, window, value):
    first = hour(window.start_time)
    first['atmosphere']['aod_550nm'] = value
    result = summarize_window_atmosphere([first], sources, window)
    assert result['status'] == 'partial'
    assert result['fields']['aod_550nm']['mean'] is None
    assert result['fields']['aod_550nm']['valid_samples'] == 0
    assert result['fields']['aod_550nm']['missing_samples'] == 2
    assert result['fields']['pm2_5_ug_m3']['mean'] == 1
    assert result['fields']['pm2_5_ug_m3']['missing_samples'] == 1
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize(
    'change',
    [
        {'time': '2026-11-08T19:01:00+08:00'},
        {'time': '2026-11-08T19:00:00'},
        {'data_kind': 'observation'},
        {'temporal_role': 'unknown'},
        {'temporal_role': []},
        {'field_sources': None},
    ],
)
def test_wrong_or_ambiguous_state_time_and_kind_stay_unknown(sources, window, change):
    record = hour(window.start_time)
    record['atmosphere'].update(change)
    result = summarize_window_atmosphere([record], sources, window)
    assert result['status'] == 'unknown'
    assert all(value['mean'] is None for value in result['fields'].values())


def test_different_offsets_are_joined_by_instant_and_clipped_end_is_not_a_full_hour(
    sources, window
):
    record = hour(window.start_time)
    record['atmosphere']['time'] = '2026-11-08T11:00:00Z'
    window.end_time = '2026-11-08T19:30:00+08:00'
    result = summarize_window_atmosphere([record], sources, window)
    assert result['expected_samples'] == 1
    assert result['status'] == 'available'


def test_no_nearest_hour_duplicate_or_unbounded_source_substitution(sources, window):
    exact = hour(window.start_time)
    records = [exact, deepcopy(exact), hour('2026-11-08T20:01:00+08:00'), {'time': 'invalid'}]
    assert summarize_window_atmosphere(records, sources, window)['status'] == 'unknown'
    sources['model']['coverage_start_time'] = '2026-11-08T20:00:00+08:00'
    result = summarize_window_atmosphere([exact], sources, window)
    assert result['status'] == 'unknown'
    sources['model']['coverage_start_time'] = None
    assert summarize_window_atmosphere([exact], sources, window)['status'] == 'unknown'


@pytest.mark.parametrize(
    'change',
    [
        {'status': 'error'},
        {'status': 'invalid'},
        {'units': {'aod_550nm': 'km'}},
        {'retrieved_at': '2026-11-01T00:00:00'},
        {'coverage_end_time': None},
    ],
)
def test_bad_source_metadata_never_earns_known_fields(sources, window, change):
    sources['model'].update(change)
    result = summarize_window_atmosphere([hour(window.start_time)], sources, window)
    assert result['status'] == 'unknown'


def test_wrong_field_source_and_absent_state_leave_weather_unaffected(sources, window):
    record = hour(window.start_time)
    record['atmosphere']['field_sources']['aod_550nm'] = ['invalid']
    result = summarize_window_atmosphere(
        [record, {'time': '2026-11-08T20:00:00+08:00'}], sources, window
    )
    assert result['fields']['aod_550nm']['mean'] is None
    assert result['status'] == 'partial'
    assert summarize_window_atmosphere([record], {}, window)['status'] == 'unknown'
    malformed = summarize_window_atmosphere([record], None, window)
    assert malformed['status'] == 'unknown'
    assert malformed['invalid_sources'] == ['atmosphere_sources']


def test_finite_large_values_and_zero_means_are_json_safe(sources, window):
    for value in (0, float.fromhex('0x1.fffffffffffffp+1023')):
        records = [hour(window.start_time, value), hour('2026-11-08T20:00:00+08:00', value)]
        result = summarize_window_atmosphere(records, sources, window)
        assert result['fields']['aod_550nm']['mean'] == value
        json.dumps(result, allow_nan=False)


@pytest.mark.parametrize(
    'start,end',
    [
        (None, None),
        ('2026-11-08T19:00:00', None),
        ('0001-01-01T00:00:00+14:00', '2026-11-08T19:00:00Z'),
        ('2026-11-08T20:00:00Z', '2026-11-08T19:00:00Z'),
    ],
)
def test_invalid_window_is_not_replaced_with_an_entire_night(start, end):
    with pytest.raises(ValueError):
        summarize_window_atmosphere([], {}, ObservationWindow(start_time=start, end_time=end))


@pytest.mark.asyncio
async def test_enrichment_cannot_change_decision_scores_windows_or_add_requests(
    sources, monkeypatch
):
    original, request = build_case('clear-continuous')
    baseline = await original.build_agent_plan(request)
    calls = []

    async def enriched(**kwargs):
        calls.append(kwargs)
        data = deepcopy(await original._dependencies.fetch_weather(**kwargs))
        for item in data['summary']['hourly']:
            # Out-of-window hours must not contaminate the selected-window mean.
            item['atmosphere'] = hour(
                item['time'],
                1
                if 19 <= datetime.fromisoformat(item['time']).hour
                or datetime.fromisoformat(item['time']).hour < 5
                else 999,
            )['atmosphere']
        data['summary']['atmosphere_sources'] = sources
        data['summary']['current'] = {'atmosphere': hour('2026-11-01T00:00:00Z', 999)['atmosphere']}
        return data

    service = PlanningService(replace(original._dependencies, fetch_weather=enriched))
    result = await service.build_agent_plan(request)
    assert result.decision.model_dump() == baseline.decision.model_dump()
    assert result.alternatives == baseline.alternatives
    assert len(calls) == 1
    facts = next(e.facts for e in result.evidence if e.kind == 'weather')
    atmosphere = facts['atmosphere']
    assert atmosphere['fields']['aod_550nm']['mean'] == 1
    assert atmosphere['fields']['aod_550nm']['valid_samples'] == 10
    assert atmosphere['status'] == 'available'
    assert any(u.code == 'atmosphere_unvalidated' for u in result.uncertainties)
    json.dumps(result.model_dump(mode='json'), allow_nan=False)
    assert (
        next(e.facts for e in baseline.evidence if e.kind == 'weather')['atmosphere']['status']
        == 'unknown'
    )
    assert any(u.code == 'atmosphere_unavailable' for u in baseline.uncertainties)

    from fastmcp import Client

    from src.functions.planning import agent_impl
    from src.server_instance import mcp

    monkeypatch.setattr(agent_impl, '_build_planning_service', lambda: service)
    async with Client(mcp._mcp) as client:
        reply = await client.call_tool(
            'plan_stargazing_session', {'request': request.model_dump(mode='json')}
        )
    assert reply.structured_content['_meta']['status'] == 'success'
    sdk_facts = next(
        e['facts'] for e in reply.structured_content['data']['evidence'] if e['kind'] == 'weather'
    )
    assert sdk_facts['atmosphere']['fields']['aod_550nm']['mean'] == 1
    assert sdk_facts['atmosphere']['affects_ranking'] is False


@pytest.mark.asyncio
async def test_selected_weather_provider_does_not_borrow_other_atmosphere(sources):
    original, request = build_case('clear-continuous')

    async def providers(**kwargs):
        data = deepcopy(await original._dependencies.fetch_weather(**kwargs))
        hours = deepcopy(data['summary']['hourly'])
        enriched_hours = [
            {**item, 'atmosphere': hour(item['time'])['atmosphere']} for item in hours
        ]
        data['providers'] = {
            'qweather': {'data': {'hourly': hours}},
            'open-meteo': {'data': {'hourly': enriched_hours[:2], 'atmosphere_sources': sources}},
        }
        data['summary']['hourly'] = enriched_hours
        data['summary']['atmosphere_sources'] = sources
        return data

    result = await PlanningService(
        replace(original._dependencies, fetch_weather=providers)
    ).build_agent_plan(request)
    facts = next(e.facts for e in result.evidence if e.kind == 'weather')
    assert facts['provider'] == 'qweather'
    assert facts['atmosphere']['status'] == 'unknown'
    assert facts['atmosphere']['sources'] == {}
