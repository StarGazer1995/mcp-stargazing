"""Regression checks for selected-window model schedules, not observed accuracy."""

from datetime import UTC, datetime

import pytest

from src.schemas.planning import ObservationWindow
from src.services.planning_targets import assess_target_windows

START = datetime(2026, 11, 8, 15, tzinfo=UTC).timestamp()
END = START + 6 * 3600
MOON = {'illumination': 0.1, 'always_down': False, 'always_up': False}
WINDOW = ObservationWindow(
    start_time='2026-11-08T23:00:00+08:00', end_time='2026-11-09T05:00:00+08:00'
)


def target(name='Synthetic', *, altitude=50.0, start=START, end=END, **kwargs):
    return {
        'name': name,
        'type': 'galaxy',
        'transit_alt': 85.0,
        'altitude_curve': [{'time': start, 'alt': altitude}, {'time': end, 'alt': altitude}],
        **kwargs,
    }


def check(targets, moon=MOON, window=WINDOW):
    return assess_target_windows(targets, moon, window, 'Asia/Shanghai')


def test_equivalent_offset_and_naive_local_bounds_use_same_instants():
    retained, facts = check([target()])
    assert retained[0]['transit_alt'] == 85.0  # Legacy peak is never redefined.
    item = facts['targets'][0]
    assert item['status'] == 'scheduler_window_available'
    assert item['slots'] == [
        {
            'start_time': '2026-11-08T15:00:00+00:00',
            'end_time': '2026-11-08T21:00:00+00:00',
            'duration_min': 360,
        }
    ]
    for start, end in [
        ('2026-11-08T15:00:00Z', '2026-11-08T21:00:00Z'),
        ('2026-11-08 23:00:00', '2026-11-09 05:00:00'),
        ('2026-11-08T10:00:00-05:00', '2026-11-08T16:00:00-05:00'),
    ]:
        _, equivalent = check([target()], window=ObservationWindow(start_time=start, end_time=end))
        assert equivalent['targets'] == facts['targets']


def test_low_altitude_and_short_runs_are_excluded_without_joint_competition():
    first, second = target('First'), target('Second', fov_fit_score=0.9)
    low = target('Below horizon', altitude=-12.8)
    retained, facts = check([first, second, low])
    assert retained == [first, second]
    assert facts['targets'][2]['status'] == 'no_scheduler_window'
    assert all(item['slots'] for item in facts['targets'][:2])
    for duration, expected in [(29, False), (30, True)]:
        short = ObservationWindow(
            start_time=WINDOW.start_time,
            end_time=datetime.fromtimestamp(START + duration * 60, UTC).isoformat(),
        )
        kept, _ = check([target(altitude=25)], window=short)
        assert bool(kept) is expected


@pytest.mark.parametrize(
    'curve',
    [
        None,
        [],
        [{'time': START, 'alt': 50}],
        [{'time': START, 'alt': 50}, {'time': START, 'alt': 50}],
        [{'time': END, 'alt': 50}, {'time': START, 'alt': 50}],
        [{'time': START, 'alt': float('nan')}, {'time': END, 'alt': 50}],
        [{'time': START, 'alt': 91}, {'time': END, 'alt': 50}],
        [{'time': True, 'alt': 50}, {'time': END, 'alt': 50}],
        [None, None],
    ],
)
def test_invalid_curve_is_unknown_reference(curve):
    original = target(altitude_curve=curve)
    kept, facts = check([original])
    assert kept == [original]
    assert facts['targets'][0]['status'] == 'unknown'
    assert facts['targets'][0]['reason']


@pytest.mark.parametrize('start,end', [(START + 60, END), (START, END - 60)])
def test_partial_curve_cannot_prove_no_window(start, end):
    original = target(altitude=-50, start=start, end=end)
    kept, facts = check([original])
    assert kept == [original]
    assert facts['targets'][0]['reason'] == 'incomplete_window_coverage'


def test_scheduler_failure_stays_unknown_and_does_not_discard_other_targets():
    malformed = target('Bad score', fov_fit_score='unknown')
    kept, facts = check([malformed, target('Good')])
    assert len(kept) == 2
    assert facts['targets'][0]['status'] == 'unknown'
    assert facts['targets'][1]['status'] == 'scheduler_window_available'


@pytest.mark.parametrize(
    'moon',
    [
        None,
        {},
        {'illumination': None},
        {
            'illumination': 0.8,
            'always_up': False,
            'always_down': False,
        },
    ],
)
def test_missing_moon_is_not_a_verified_scheduler_window(moon):
    kept, facts = check([target(), target('Low', altitude=-50)], moon=moon)
    assert len(kept) == 1
    assert facts['moon_status'] == 'unknown_altitude_only'
    assert [item['status'] for item in facts['targets']] == [
        'altitude_window_available',
        'no_altitude_window',
    ]


def test_moonset_delay_and_always_up_warning_use_shared_policy():
    moon = {**MOON, 'illumination': 0.8, 'phase': 'Bright', 'moonset': END + 3600}
    kept, facts = check([target()], moon=moon)
    assert not kept
    assert facts['targets'][0]['status'] == 'no_scheduler_window'
    moon['moonset'] = START + 3600
    _, facts = check([target()], moon=moon)
    assert facts['targets'][0]['slots'][0]['start_time'] == '2026-11-08T16:10:00+00:00'
    moon['always_up'] = True
    moon.pop('moonset')
    kept, facts = check([target()], moon=moon)
    assert kept
    assert any('narrowband' in warning for warning in facts['targets'][0]['warnings'])


@pytest.fixture
def evening_only_target():
    """Physical geometry of artificial coordinates; no catalog or field claim."""
    import astropy.units as u
    import numpy as np
    from astropy.coordinates import AltAz, EarthLocation, SkyCoord
    from astropy.time import Time
    from astropy.utils import iers

    stamps = np.arange(1794130200, 1794177000 + 1, 900)
    with iers.conf.set_temp('auto_download', False):
        alts = (
            SkyCoord(ra=287.0262259828129 * u.deg, dec=0 * u.deg)
            .transform_to(
                AltAz(
                    obstime=Time(stamps, format='unix'),
                    location=EarthLocation(lat=30.5 * u.deg, lon=119.5 * u.deg),
                    pressure=0 * u.hPa,
                )
            )
            .alt.deg
        )
    assert max(alts) == pytest.approx(52.9425131486456, abs=0.02)
    assert max(alts[(stamps >= START) & (stamps < END)]) < -12
    original = target(
        altitude_curve=[{'time': float(t), 'alt': float(a)} for t, a in zip(stamps, alts)],
        transit_alt=float(max(alts)),
    )
    return original


def test_astropy_evening_only_counterexample(evening_only_target):
    kept, facts = check([evening_only_target])
    assert kept == []
    assert facts['targets'][0]['status'] == 'no_scheduler_window'


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['matched', 'generic', 'failure', 'all_excluded', 'invalid'])
async def test_primary_planner_uses_selected_window_without_reranking(evening_only_target, mode):
    import json

    from src.schemas import (
        AgentEquipmentIntent,
        AgentLocationIntent,
        AgentPlanningRequest,
        EquipmentPreset,
        GeoPoint,
        NightWindow,
    )
    from src.services.planning import PlanningDependencies, PlanningService

    async def search(**_kwargs):
        return {'items': [{'name': 'Synthetic site', 'lat': 30.5, 'lon': 119.5, 'score': 85}]}

    async def weather(**_kwargs):
        return {
            'summary': {
                'hourly': [
                    {
                        'time': datetime.fromtimestamp(START + hour * 3600, UTC).isoformat(),
                        'cloud_cover_percent': 5,
                        'precipitation_probability': 0,
                        'wind_speed_kph': 6,
                    }
                    for hour in range(6)
                ]
            }
        }

    async def forecast(**_kwargs):
        return {'deep_sky': [{**evening_only_target, 'score': 99}]}

    async def night(*_args):
        return NightWindow(
            local_date='2026-11-08',
            civil_dusk='2026-11-08T17:30:00+08:00',
            civil_dawn='2026-11-09T06:30:00+08:00',
            duration_hours=13,
            time_zone='Asia/Shanghai',
        )

    async def equipment(**_kwargs):
        if mode == 'failure':
            raise RuntimeError('Synthetic matcher failure')
        if mode == 'all_excluded':
            return {'targets': [evening_only_target], 'moon': MOON}
        if mode == 'invalid':
            return {'targets': [target(suitability_score='invalid')], 'moon': MOON}
        return {
            'targets': [evening_only_target, target('Good'), {'name': 'Reference'}],
            'moon': MOON,
        }

    request = AgentPlanningRequest(
        location=AgentLocationIntent(center=GeoPoint(lat=30.5, lon=119.5)),
        start_date='2026-11-08',
        nights=1,
        equipment=(
            AgentEquipmentIntent(preset=EquipmentPreset.SEESTAR_S50) if mode != 'generic' else None
        ),
    )
    service = PlanningService(
        PlanningDependencies(
            search_places=search,
            fetch_weather=weather,
            fetch_forecast=forecast,
            fetch_night_window=night,
            fetch_equipment_targets=equipment,
            now=lambda: datetime(2026, 11, 8, tzinfo=UTC),
        )
    )
    result = await service.build_agent_plan(request)
    assert result.decision is not None
    assert (
        datetime.fromisoformat(result.decision.observation_window.start_time).timestamp() == START
    )
    assert datetime.fromisoformat(result.decision.observation_window.end_time).timestamp() == END
    assert result.decision.recommendation_score == result.decision.score_breakdown.final_score
    evidence = next(e for e in result.evidence if e.source == 'selected_target_window_check')
    if mode == 'matched':
        assert [t.name for t in result.decision.targets] == ['Good', 'Reference']
        assert [t['status'] for t in evidence.facts['targets']] == [
            'no_scheduler_window',
            'scheduler_window_available',
            'unknown',
        ]
        assert {u.code for u in result.uncertainties} >= {
            'target_window_unverified',
            'target_window_exclusions',
        }
    elif mode == 'all_excluded':
        assert result.decision.targets == []
        assert evidence.facts['targets'][0]['status'] == 'no_scheduler_window'
        assert 'target_window_exclusions' in {u.code for u in result.uncertainties}
    else:
        assert result.decision.targets[0].name == evening_only_target['name']
        assert evidence.facts['assessment_scope'] == 'generic_reference_only'
        assert evidence.facts['targets'][0]['status'] == 'unknown'
    baseline = await service.build_agent_plan(request.model_copy(update={'equipment': None}))
    assert result.decision.model_dump(
        exclude={'targets', 'equipment'}
    ) == baseline.decision.model_dump(exclude={'targets', 'equipment'})
    # Free-form evidence remains JSON-safe and uses the existing public models.
    assert isinstance(json.loads(result.model_dump_json())['decision']['targets'], list)
    if mode == 'matched':
        from unittest.mock import patch

        from fastmcp import Client

        from src.functions.planning.agent_impl import mcp

        with patch(
            'src.functions.planning.agent_impl._build_planning_service', return_value=service
        ):
            async with Client(mcp._mcp) as client:
                response = await client.call_tool(
                    'plan_stargazing_session', {'request': request.model_dump(mode='json')}
                )
        payload = response.structured_content
        assert payload['_meta']['status'] == 'success'
        assert [item['name'] for item in payload['data']['decision']['targets']] == [
            'Good',
            'Reference',
        ]
        assert (
            next(
                item['facts']
                for item in payload['data']['evidence']
                if item['source'] == 'selected_target_window_check'
            )
            == evidence.facts
        )
