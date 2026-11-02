"""The target and schedule tools must interpret an explicit observation instant identically."""

from datetime import UTC, datetime, timedelta

import pytest
from fastmcp import Client

import src.main  # noqa: F401
from src.functions.telescope import impl
from src.server_instance import mcp


@pytest.fixture
def matching(monkeypatch):
    seen = []

    def match(_config, _observer, stamp, _limit):
        start = stamp.to_datetime(timezone=UTC)
        end = start + timedelta(hours=2)
        seen.append(start)
        return {
            'targets': [
                {
                    'name': 'Synthetic clock target',
                    'type': 'galaxy',
                    'civil_dusk': start.replace(tzinfo=None).isoformat(),
                    'civil_dawn': end.replace(tzinfo=None).isoformat(),
                    'fov_fit_score': 1.0,
                    'surface_brightness_score': 1.0,
                    'filter_match_score': 1.0,
                    'suitability_score': 90.0,
                    'altitude_curve': [
                        {'time': (start + timedelta(minutes=minutes)).timestamp(), 'alt': 60.0}
                        for minutes in range(0, 121, 15)
                    ],
                }
            ],
            'moon': {'always_down': True, 'always_up': False, 'illumination': 0, 'phase': 'New'},
        }

    monkeypatch.setattr(impl, 'match_telescope_targets', match)
    return seen


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'time,zone',
    [
        ('2026-11-08T20:00:00+08:00', 'Asia/Shanghai'),
        ('2026-11-08T12:00:00Z', 'Asia/Shanghai'),
        ('2026-11-08T07:00:00-05:00', 'Asia/Shanghai'),
        ('2026-11-09T02:00:00+14:00', 'Asia/Shanghai'),
        ('2026-11-08T20:00:00', 'Asia/Shanghai'),
        ('2026-11-08T12:00:00', 'UTC'),
    ],
)
async def test_target_and_schedule_tools_preserve_the_same_instant(matching, time, zone):
    kwargs = dict(focal_length_mm=250, lon=120, lat=30, time=time, time_zone=zone)
    targets = await impl.get_telescope_targets.fn(**kwargs)
    schedule = await impl.get_shooting_plan.fn(**kwargs)
    expected = datetime(2026, 11, 8, 12, tzinfo=UTC)
    assert matching == [expected, expected]
    assert targets['_meta']['status'] == schedule['_meta']['status'] == 'success'
    assert schedule['data']['targets'] == targets['data']['targets']
    plan = schedule['data']['plan']
    assert plan['used_min'] == plan['total_dark_min'] == 120
    assert len(plan['slots']) == 1
    assert datetime.fromisoformat(plan['slots'][0]['start_time']) == expected
    assert datetime.fromisoformat(plan['slots'][0]['end_time']) == expected + timedelta(hours=2)


@pytest.mark.asyncio
@pytest.mark.parametrize('time', ['2026-11-08T20:00:00+08:00', '2026-11-08T12:00:00Z'])
async def test_real_sdk_accepts_offset_times_for_shooting_slots(matching, time):
    async with Client(mcp._mcp) as client:
        reply = await client.call_tool(
            'get_shooting_plan',
            {
                'focal_length_mm': 250,
                'lon': 120,
                'lat': 30,
                'time': time,
                'time_zone': 'Asia/Shanghai',
            },
        )
    assert reply.structured_content['_meta']['status'] == 'success'
    assert reply.structured_content['data']['plan']['used_min'] == 120
    assert matching == [datetime(2026, 11, 8, 12, tzinfo=UTC)]


@pytest.mark.asyncio
async def test_offset_time_with_no_targets_returns_empty_plan(monkeypatch):
    monkeypatch.setattr(
        impl,
        'match_telescope_targets',
        lambda *_: {
            'targets': [],
            'moon': {'phase': 'New', 'illumination': 0, 'always_down': True},
        },
    )
    result = await impl.get_shooting_plan.fn(
        focal_length_mm=250,
        lon=120,
        lat=30,
        time='2026-11-08T20:00:00+08:00',
        time_zone='Asia/Shanghai',
    )
    plan = result['data']['plan']
    assert plan['slots'] == [] and plan['used_min'] == plan['total_dark_min'] == 0
    assert datetime.fromisoformat(plan['dusk']) == datetime(2026, 11, 8, 12)
