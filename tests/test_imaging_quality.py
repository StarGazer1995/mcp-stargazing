"""Policy acceptance, astronomical clipping, timing and benchmark behavior."""

from dataclasses import replace
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from evaluations.imaging_quality import CASES, build_case
from evaluations.planning_benchmark import run_case, summarize
from src.response import MCPError
from src.schemas import ObservationStyle
from src.services.planning import PlanningService, _pick_best_observation_window
from src.services.planning_quality import fetch_imaging_bounds


@pytest.mark.asyncio
@pytest.mark.parametrize('name,expected', CASES.items())
async def test_imaging_policy_acceptance(name, expected):
    service, request = build_case(name)
    result = await service.build_agent_plan(request)
    assert (result.decision is not None) == expected
    if expected:
        window = result.decision.observation_window
        assert window.start_time == '2026-11-08T19:00:00+08:00'
        assert window.end_time == '2026-11-09T05:00:00+08:00'
        weather = next(e for e in result.evidence if e.kind == 'weather')
        assert weather.facts['imaging_policy']['version'] == 'deep-sky-v1'
        assert weather.facts['astronomical_bounds']
    else:
        assert not result.alternatives
        assert any(e.source == 'unranked_planning_reference' for e in result.evidence)


def test_strict_window_requires_two_hours_and_reports_worst_conditions():
    start = datetime.fromisoformat('2026-11-08T23:00:00+08:00')
    hours = [
        {
            'time': (start + timedelta(hours=i)).isoformat(),
            'cloud_cover_percent': c,
            'precipitation_probability': p,
            'wind_speed_kph': w,
        }
        for i, c, p, w in [(0, 1, 0.1, 6), (1, 25, 0.2, 20)]
    ]
    bounds = (start, start + timedelta(hours=2))
    kwargs = {'observation_style': ObservationStyle.DEEP_SKY, 'imaging_bounds': bounds}
    window = _pick_best_observation_window(hours, start.isoformat(), 'Asia/Shanghai', **kwargs)
    assert window.duration_hours == 2
    assert window.cloud_cover_percent == 25
    assert window.precipitation_probability == 0.2
    assert window.wind_speed_kph == 20
    # Duplicate timestamps and sub-hour gaps cannot manufacture a continuous run.
    assert (
        _pick_best_observation_window(hours[:1] * 3, start.isoformat(), 'Asia/Shanghai', **kwargs)
        is None
    )
    hours[1]['time'] = (start + timedelta(minutes=90)).isoformat()
    assert (
        _pick_best_observation_window(hours, start.isoformat(), 'Asia/Shanghai', **kwargs) is None
    )


@pytest.mark.asyncio
async def test_actual_darkness_solver_uses_minus_eighteen_degrees():
    from astropy.coordinates import AltAz, EarthLocation, get_sun
    from astropy.time import Time

    reference = datetime.fromisoformat('2026-11-08T12:00:00+08:00')
    dusk, dawn = await fetch_imaging_bounds(30.5, 119.5, reference)
    assert dusk.date() == reference.date()
    assert dawn > dusk
    frame = AltAz(obstime=Time([dusk, dawn]), location=EarthLocation.from_geodetic(119.5, 30.5))
    elevations = get_sun(frame.obstime).transform_to(frame).alt.deg
    assert all(abs(value + 18) < 0.1 for value in elevations)


@pytest.mark.asyncio
async def test_provider_timing_separates_cache_hits_and_errors():
    events = []
    service, request = build_case('clear-continuous', events.append)
    request.nights = 2
    await service.build_agent_plan(request)
    for stage in ['search_places', 'fetch_weather']:
        calls = [e for e in events if e['stage'] == stage]
        assert sum(not e['cache_hit'] for e in calls) == 1
        assert any(e['cache_hit'] for e in calls)
    assert all(e['elapsed_seconds'] >= 0 for e in events)

    async def failing(**_kwargs):
        raise MCPError(MCPError.API_TIMEOUT, 'test timeout')

    service = PlanningService(replace(service._dependencies, fetch_weather=failing))
    await service.build_agent_plan(request)
    assert any(e['stage'] == 'fetch_weather' and e['outcome'] == 'error' for e in events)


@pytest.mark.asyncio
async def test_timing_observer_failure_does_not_break_planning():
    def broken(_event):
        raise RuntimeError('observer failed')

    service, request = build_case('clear-continuous', broken)
    assert (await service.build_agent_plan(request)).decision is not None


@pytest.mark.asyncio
async def test_benchmark_separates_execution_from_wrong_expectations():
    good = await run_case(
        {'id': 'clear-continuous', 'expected_decision': True}, mode='frozen', url=None, timeout=1
    )
    wrong = await run_case(
        {'id': 'cloudy-74-percent', 'expected_decision': True}, mode='frozen', url=None, timeout=1
    )
    error = await run_case(
        {'id': 'not-a-case', 'expected_decision': True}, mode='frozen', url=None, timeout=1
    )
    assert good['execution_success'] and good['expectation_passed']
    assert wrong['execution_success'] and not wrong['expectation_passed']
    assert not error['execution_success']
    report = summarize([good, wrong, error])
    assert report['attempts'] == 3
    assert report['execution_successes'] == 2
    assert report['expectation_passes'] == 1
    assert good['forecast_accuracy_verified'] is False


@pytest.mark.asyncio
async def test_live_benchmark_marks_null_decision_as_success(monkeypatch):
    service, request = build_case('missing-rain')
    data = (await service.build_agent_plan(request)).model_dump(mode='json')

    class Client:
        def __init__(self, *_args, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            pass

        async def call_tool(self, *_args, **_kwargs):
            return SimpleNamespace(
                structured_content={'_meta': {'status': 'success'}, 'data': data}
            )

    monkeypatch.setattr('fastmcp.Client', Client)
    sample = await run_case(
        {'id': 'live-unknown', 'request': request.model_dump(mode='json')},
        mode='live',
        url='test',
        timeout=1,
    )
    assert sample['execution_success']
    assert sample['expectation_passed'] is None
    assert sample['stages'] == []


def test_forecast_verification_rejects_wrong_site_time_or_forecast_as_truth():
    from copy import deepcopy

    from evaluations.forecast_verification import verify

    pair = {
        'site_id': 'ridge',
        'valid_time': '2026-11-08T20:00:00+08:00',
        'forecast': {
            'source': 'provider',
            'issued_at': '2026-11-01T20:00:00+08:00',
            'effective_cloud_percent': 20,
            'precipitation_probability': 0.2,
        },
        'observation': {
            'site_id': 'ridge',
            'valid_time': '2026-11-08T20:00:00+08:00',
            'source': 'observing-log',
            'kind': 'observation',
            'effective_cloud_percent': 30,
            'precipitation_occurred': False,
        },
    }
    wrong_site = deepcopy(pair)
    wrong_site['observation']['site_id'] = 'elsewhere'
    wrong_time = deepcopy(pair)
    wrong_time['observation']['valid_time'] = '2026-11-08T21:00:00+08:00'
    not_observed = deepcopy(pair)
    not_observed['observation']['kind'] = 'forecast'
    report = verify([pair, wrong_site, wrong_time, not_observed])
    assert report['matched_pairs'] == 1
    assert len(report['rejected']) == 3
    assert report['cloud_mae_percentage_points'] == 10
    assert report['rain_brier_score'] == pytest.approx(0.04)
    assert report['lead_hours'] == [168]


@pytest.mark.asyncio
async def test_missing_civil_window_does_not_shift_predawn_to_next_evening():
    service, _request = build_case('clear-continuous')
    seen = []

    async def darkness(_lat, _lon, reference):
        seen.append(reference)
        return reference.replace(hour=19), (reference + timedelta(days=1)).replace(hour=5)

    service = PlanningService(replace(service._dependencies, fetch_imaging_bounds=darkness))
    location = SimpleNamespace(lat=30.5, lon=119.5)
    for stamp in ['2026-11-08T23:00:00+08:00', '2026-11-09T02:00:00+08:00']:
        await service._imaging_bounds(
            location,
            datetime.fromisoformat(stamp),
            'Asia/Shanghai',
            None,
            ObservationStyle.DEEP_SKY,
        )
    assert [value.isoformat() for value in seen] == ['2026-11-08T12:00:00+08:00'] * 2
