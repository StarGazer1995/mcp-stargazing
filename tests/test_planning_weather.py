"""Regressions for dated night forecasts in the public planning workflow."""

from datetime import UTC, datetime, timedelta

import pytest

from src.functions.weather.providers.open_meteo import _build_open_meteo_params
from src.schemas import (
    AgentPlanningRequest,
    EvidenceKind,
    NightWindow,
    ObservationStyle,
    StargazingLocation,
)
from src.services.planning import (
    PlanningDependencies,
    PlanningService,
    _compute_recommendation_score,
    _pick_best_observation_window,
)
from src.services.planning_weather import select_night_weather


def window(day=6):
    return NightWindow(
        local_date=f'2026-11-{day:02d}',
        civil_dusk=f'2026-11-{day:02d}T17:30:00+08:00',
        civil_dawn=f'2026-11-{day + 1:02d}T06:30:00+08:00',
        duration_hours=13.0,
        time_zone='Asia/Shanghai',
    )


def dated_weather():
    hours = []
    for day, layer, cloud in ((6, 'high', 100), (7, 'mid', 60), (8, 'low', 0)):
        dusk = datetime.fromisoformat(f'2026-11-{day:02d}T18:00:00+08:00')
        hours.extend(
            {
                'time': (dusk + timedelta(hours=i)).isoformat(),
                'cloud_cover_percent': 0.0,
                f'cloud_cover_{layer}_percent': float(cloud),
                'precipitation_probability': 0.0,
                'wind_speed_kph': 5.0,
            }
            for i in range(13)
        )
    return {
        'summary': {
            'current': {'cloud_cover_percent': 14.0, 'visibility_km': 19.38},
            'daily': [{'date': '2026-11-06', 'cloud_cover_percent': 1}],
            'hourly': hours,
        }
    }


@pytest.mark.asyncio
async def test_three_nights_use_distinct_hourly_layers_and_reuse_only_raw_inputs():
    calls = {'places': 0, 'weather': 0}

    async def places(**_kwargs):
        calls['places'] += 1
        return {'items': [{'name': 'Ridge', 'lat': 30.485, 'lon': 119.468, 'score': 70}]}

    async def weather(**_kwargs):
        calls['weather'] += 1
        return dated_weather()

    async def targets(**_kwargs):
        return {'deep_sky': [], 'moon_phase': {'illumination': 0.07}}

    async def night(_lat, _lon, reference):
        if reference.hour < 12:
            reference -= timedelta(days=1)
        return window(reference.day)

    async def equipment(**_kwargs):
        return {'targets': [{'name': 'M31', 'suitability_score': 80, 'transit_alt': 65}]}

    service = PlanningService(
        PlanningDependencies(
            search_places=places,
            fetch_weather=weather,
            fetch_forecast=targets,
            fetch_night_window=night,
            fetch_equipment_targets=equipment,
            now=lambda: datetime(2026, 10, 27, tzinfo=UTC),
        )
    )
    request = AgentPlanningRequest.model_validate(
        {
            'location': {'center': {'lat': 30.485, 'lon': 119.468}, 'radius_km': 15},
            'start_date': '2026-11-06',
            'nights': 3,
            'observation_style': 'deep_sky',
            'equipment': {'preset': 'hope_d60_asi2600mc_air'},
            'candidate_limit': 3,
        }
    )
    result = await service.build_agent_plan(request)
    assert result.decision.date == '2026-11-08'
    scores = {result.decision.score_breakdown.weather_base_score}
    scores.update(alt.score_breakdown.weather_base_score for alt in result.alternatives)
    assert len(scores) == 3
    assert max(scores) <= 100
    assert calls == {'places': 1, 'weather': 1}
    evidence = next(item for item in result.evidence if item.kind == EvidenceKind.WEATHER)
    assert evidence.facts['cloud_cover_percent'] == 0
    assert evidence.facts['visibility_km'] is None  # current visibility was not copied
    assert evidence.facts['time_basis'] == 'night_hourly_forecast'
    assert evidence.facts['interval_start'] == window(8).civil_dusk
    assert result.decision.observation_window.start_time == '2026-11-08T18:00:00+08:00'
    assert result.decision.observation_window.end_time == '2026-11-09T06:30:00+08:00'
    assert result.decision.targets[0].transit_alt == 65
    assert any(item.code == 'long_range_forecast' for item in result.uncertainties)
    # A new request must refetch rather than inherit a previous weather snapshot.
    await service.build_agent_plan(request)
    assert calls == {'places': 2, 'weather': 2}


def test_no_forecast_coverage_never_substitutes_current_daily_or_null_hours():
    data = dated_weather()
    data['summary']['hourly'] = [
        {},
        {'time': 'broken'},
        {'time': '2026-11-06T19:00:00+08:00', 'cloud_cover_percent': float('nan')},
        {'time': '2026-10-27T19:00:00+08:00', 'cloud_cover_percent': 1},
    ]
    result = select_night_weather(data, window().civil_dusk, 'Asia/Shanghai', window())
    assert result.summary is None
    assert result.hourly == []
    assert result.notes[0].startswith('nightly_weather_unavailable:')


def test_provider_horizon_fallback_and_naive_provider_timezone_are_respected():
    data = {
        'providers': {
            'open-meteo': {
                'data': {
                    'hourly': [
                        {'time': '2026-10-27T19:00:00+08:00', 'cloud_cover_percent': 0},
                    ]
                }
            },
            'qweather': {
                'data': {
                    'location': {'timezone': 'UTC'},
                    'hourly': [
                        {'time': '2026-11-06T12:00:00', 'cloud_cover_percent': 80},
                    ],
                }
            },
        }
    }
    result = select_night_weather(data, window().civil_dusk, 'Asia/Shanghai', window())
    assert result.summary.cloud_cover_percent == 80
    assert result.facts['provider'] == 'qweather'
    assert result.hourly[0]['time'] == '2026-11-06T20:00:00+08:00'
    assert result.notes[0].startswith('nightly_weather_partial:')


def test_opaque_high_cloud_is_not_a_clear_observation_window():
    result = _pick_best_observation_window(
        dated_weather()['summary']['hourly'],
        window().civil_dusk,
        'Asia/Shanghai',
        night_window=window(),
    )
    assert result is None


@pytest.mark.parametrize(
    'hours',
    [
        [],
        [
            {
                'time': '2026-11-06T20:00:00+08:00',
                'cloud_cover_percent': 0,
                'precipitation_probability': 0.9,
            },
        ],
    ],
)
@pytest.mark.asyncio
async def test_missing_or_unusable_forecasts_are_explicit_high_uncertainty(hours):
    async def places(**_kwargs):
        return {'items': [{'name': 'Ridge', 'lat': 30.485, 'lon': 119.468, 'score': 70}]}

    async def weather(**_kwargs):
        return {'summary': {'current': {'cloud_cover_percent': 0}, 'hourly': hours}}

    async def targets(**_kwargs):
        return {'deep_sky': []}

    async def night(_lat, _lon, _reference):
        return window()

    service = PlanningService(
        PlanningDependencies(
            search_places=places,
            fetch_weather=weather,
            fetch_forecast=targets,
            fetch_night_window=night,
            now=lambda: datetime(2026, 10, 27, tzinfo=UTC),
        )
    )
    result = await service.build_agent_plan(
        AgentPlanningRequest.model_validate(
            {
                'location': {'center': {'lat': 30.485, 'lon': 119.468}},
                'start_date': '2026-11-06',
                'nights': 1,
            }
        )
    )
    code = 'no_usable_observation_window' if hours else 'nightly_weather_unavailable'
    assert any(item.code == code and item.level == 'high' for item in result.uncertainties)
    assert result.decision.observation_window is None
    assert '天气更晴朗' not in result.decision.reason_summary
    if hours:
        assert result.decision.score_breakdown.weather_base_score == 0
    assert '_weather_evidence' not in result.model_dump()['decision']


def test_unknown_weather_stays_neutral_but_known_rain_cannot_earn_clear_credit():
    rainy = select_night_weather(
        {
            'summary': {
                'hourly': [
                    {
                        'time': '2026-11-06T20:00:00+08:00',
                        'cloud_cover_percent': 0,
                        'precipitation_probability': 0.9,
                    }
                ]
            }
        },
        window().civil_dusk,
        'Asia/Shanghai',
        window(),
    )
    assert rainy.summary.weather_text == 'Rain risk'
    score = _compute_recommendation_score(
        StargazingLocation(name='Ridge', lat=30.485, lon=119.468, score=70),
        rainy.summary,
        None,
        0.07,
        ObservationStyle.DEEP_SKY,
        0.0,
    )
    assert score.weather_base_score == 0


def test_open_meteo_requests_the_extended_forecast_horizon():
    assert _build_open_meteo_params(30.485, 119.468, 'Asia/Shanghai')['forecast_days'] == 16
