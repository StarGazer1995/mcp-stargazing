"""Transport-independent tests for the planning application service."""

from datetime import UTC, datetime

import pytest

from src.response import MCPError
from src.schemas import (
    NightWindow,
    ObservationStyle,
    ObservationWindow,
    PlanningTarget,
    StargazingLocation,
)
from src.services.planning import (
    PlanningDependencies,
    PlanningService,
    _build_recommendation_reasons,
    _pick_best_observation_window,
)


def _night_window(local_date: str = '2024-06-15') -> NightWindow:
    return NightWindow(
        local_date=local_date,
        civil_dusk=f'{local_date}T20:30:00+08:00',
        civil_dawn='2024-06-16T04:30:00+08:00',
        duration_hours=8.0,
        time_zone='Asia/Shanghai',
    )


def _service(*, weather_failure: bool = False) -> PlanningService:
    async def search_places(**_kwargs):
        return {
            'resource_id': 'analysis-service-test',
            'items': [
                {
                    'name': 'Transport-Free Ridge',
                    'lat': 40.1,
                    'lon': 116.1,
                    'score': 86.0,
                    'bortle_class': 3,
                }
            ],
        }

    async def fetch_weather(**_kwargs):
        if weather_failure:
            raise MCPError(MCPError.API_TIMEOUT, 'weather timed out')
        return {
            'summary': {
                'current': {
                    'weather_text': 'Clear',
                    'cloud_cover_percent': 8.0,
                    'visibility_km': 20.0,
                    'wind_speed_kph': 6.0,
                },
                'hourly': [],
            }
        }

    async def fetch_forecast(**_kwargs):
        return {
            'moon_phase': {'phase_name': 'New Moon', 'illumination': 0.02},
            'planets': [{'name': 'Jupiter'}],
            'deep_sky': [{'name': 'M31', 'type': 'galaxy', 'score': 90.0}],
        }

    async def fetch_night_window(_lat, _lon, _reference):
        return _night_window()

    return PlanningService(
        PlanningDependencies(
            search_places=search_places,
            fetch_weather=fetch_weather,
            fetch_forecast=fetch_forecast,
            fetch_night_window=fetch_night_window,
            now=lambda: datetime(2026, 10, 24, 9, 0, tzinfo=UTC),
        )
    )


def test_observation_window_prefers_continuous_dark_run():
    window = _pick_best_observation_window(
        [
            {'time': '2024-06-15T20:00:00+08:00', 'cloud_cover_percent': 1.0},
            {
                'time': '2024-06-15T21:00:00+08:00',
                'cloud_cover_percent': 5.0,
                'precipitation_probability': 0.0,
                'wind_speed_kph': 8.0,
            },
            {
                'time': '2024-06-15T22:00:00+08:00',
                'cloud_cover_percent': 5.0,
                'precipitation_probability': 0.0,
                'wind_speed_kph': 8.0,
            },
            {
                'time': '2024-06-15T23:00:00+08:00',
                'cloud_cover_percent': 90.0,
                'precipitation_probability': 0.0,
            },
            {
                'time': '2024-06-16T00:00:00+08:00',
                'cloud_cover_percent': 15.0,
                'precipitation_probability': 0.0,
            },
        ],
        '2024-06-15 20:00:00',
        'Asia/Shanghai',
        night_window=_night_window(),
        moon_illumination=0.8,
        top_targets=[PlanningTarget(name='M31', category='galaxy', transit_alt=45.0)],
    )

    assert window is not None
    assert window.start_time == '2024-06-15T21:00:00+08:00'
    assert window.end_time == '2024-06-15T23:00:00+08:00'
    assert window.duration_hours == 2.0
    assert window.quality_score is not None
    assert window.quality_score > 95.0


def test_observation_window_falls_back_to_best_single_bad_hour():
    window = _pick_best_observation_window(
        [
            {
                'time': '2024-06-15T21:00:00+08:00',
                'cloud_cover_percent': 95.0,
                'precipitation_probability': 0.8,
            },
            {
                'time': '2024-06-15T22:00:00+08:00',
                'cloud_cover_percent': 85.0,
                'precipitation_probability': 0.5,
            },
        ],
        '2024-06-15 20:00:00',
        'Asia/Shanghai',
    )

    assert window is not None
    assert window.start_time == '2024-06-15T22:00:00+08:00'
    assert window.duration_hours == 1.0


def test_observation_window_skips_malformed_and_out_of_range_hours():
    window = _pick_best_observation_window(
        [
            {},
            {'time': 'not-a-time'},
            {'time': '2024-06-15T19:00:00+08:00'},
            {'time': '2024-06-16T09:00:00+08:00'},
            {'time': '2024-06-15T21:00:00+08:00', 'cloud_cover_percent': 10.0},
            {'time': '2024-06-15T23:00:00+08:00', 'cloud_cover_percent': 10.0},
        ],
        '2024-06-15 20:00:00',
        'Asia/Shanghai',
        night_window=NightWindow(
            local_date='2024-06-15',
            civil_dusk='not-a-time',
            civil_dawn='not-a-time',
            duration_hours=8.0,
            time_zone='Asia/Shanghai',
        ),
    )

    assert window is not None
    assert window.start_time == '2024-06-15T21:00:00+08:00'
    assert window.end_time == '2024-06-15T22:00:00+08:00'


def test_recommendation_reasons_keep_legacy_single_hour_wording():
    reasons = _build_recommendation_reasons(
        StargazingLocation(name='Test Ridge', lat=40.0, lon=116.0, score=80.0),
        None,
        ObservationWindow(start_time='2024-06-15T21:00:00+08:00'),
        None,
        [],
        ObservationStyle.BALANCED,
        [],
    )

    assert reasons[-1] == '建议优先在 2024-06-15T21:00:00+08:00 附近观测。'


@pytest.mark.asyncio
async def test_planning_service_runs_without_mcp_response_envelopes():
    plan = await _service().build_best_plan(
        south=40.0,
        west=116.0,
        north=40.5,
        east=116.5,
        time='2024-06-15 22:00:00',
        time_zone='Asia/Shanghai',
        candidate_limit=1,
    )

    assert plan.query.analysis_resource_id == 'analysis-service-test'
    assert plan.summary.generated_at == '2026-10-24T09:00:00+00:00'
    assert plan.summary.recommended_location_name == 'Transport-Free Ridge'
    assert plan.candidates[0].weather_summary.cloud_cover_percent == 8.0
    assert plan.candidates[0].top_targets[0].name == 'M31'


@pytest.mark.asyncio
async def test_planning_service_preserves_partial_results_when_weather_fails():
    plan = await _service(weather_failure=True).build_best_plan(
        south=40.0,
        west=116.0,
        north=40.5,
        east=116.5,
        time='2024-06-15 22:00:00',
        time_zone='Asia/Shanghai',
        candidate_limit=1,
    )

    assert plan.summary.total_candidates == 1
    assert plan.candidates[0].weather_summary is None
    assert plan.candidates[0].top_targets[0].name == 'M31'
    assert plan.summary.warnings == ['天气摘要降级处理：API_TIMEOUT: weather timed out']


@pytest.mark.asyncio
async def test_spatial_weather_can_reverse_regional_ranking():
    locations = [
        {
            'name': 'Static Leader',
            'lat': 40.10,
            'lon': 116.10,
            'score': 80.0,
            'bortle_class': 3,
        },
        {
            'name': 'Static Runner',
            'lat': 40.20,
            'lon': 116.20,
            'score': 78.0,
            'bortle_class': 3,
        },
        {
            'name': 'Static Third',
            'lat': 40.30,
            'lon': 116.30,
            'score': 76.0,
            'bortle_class': 4,
        },
        {
            'name': 'Regional Clear Ridge',
            'lat': 40.40,
            'lon': 116.40,
            'score': 72.0,
            'bortle_class': 4,
        },
    ]
    forecast_calls: list[float] = []

    async def search_places(**_kwargs):
        return {'resource_id': 'spatial-test', 'items': locations}

    async def fetch_weather(**_kwargs):
        return {
            'summary': {
                'current': {
                    'weather_text': 'Cloudy',
                    'cloud_cover_percent': 50.0,
                    'visibility_km': 10.0,
                    'wind_speed_kph': 5.0,
                },
                'hourly': [],
            }
        }

    async def fetch_spatial_weather(**_kwargs):
        return {
            'samples': [
                {'cloud_cover_percent': 100.0},
                {'cloud_cover_percent': 100.0},
                {'cloud_cover_percent': 100.0},
                {'cloud_cover_percent': 0.0},
            ]
        }

    async def fetch_forecast(**kwargs):
        forecast_calls.append(float(kwargs['lat']))
        return {
            'moon_phase': {'phase_name': 'New Moon', 'illumination': 0.02},
            'planets': [],
            'deep_sky': [],
        }

    async def fetch_night_window(_lat, _lon, _reference):
        return _night_window()

    service = PlanningService(
        PlanningDependencies(
            search_places=search_places,
            fetch_weather=fetch_weather,
            fetch_forecast=fetch_forecast,
            fetch_night_window=fetch_night_window,
            fetch_spatial_weather=fetch_spatial_weather,
            now=lambda: datetime(2026, 10, 24, 9, 0, tzinfo=UTC),
        )
    )

    plan = await service.build_best_plan(
        south=40.0,
        west=116.0,
        north=40.5,
        east=116.5,
        time='2024-06-15 22:00:00',
        time_zone='Asia/Shanghai',
        candidate_limit=1,
        max_locations=4,
    )

    assert plan.summary.recommended_location_name == 'Regional Clear Ridge'
    assert len(forecast_calls) == 3
    assert '区域空间天气参考云量约 0%，已用于区域比较。' in plan.candidates[0].notes


@pytest.mark.asyncio
async def test_planning_service_raises_structured_validation_errors():
    with pytest.raises(MCPError) as error:
        await _service().build_best_plan(
            south=40.5,
            west=116.0,
            north=40.0,
            east=116.5,
            time='2024-06-15 22:00:00',
            time_zone='Asia/Shanghai',
        )

    assert error.value.code == MCPError.CONFIGURATION_ERROR
    assert error.value.details == {'south': 40.5, 'north': 40.0}
