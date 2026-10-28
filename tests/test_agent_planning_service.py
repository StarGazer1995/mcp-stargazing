"""Contract tests for the agent-native planning service."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from src.response import MCPError
from src.schemas import (
    AgentEquipmentIntent,
    AgentLocationIntent,
    AgentPlanningRequest,
    EquipmentPreset,
    EvidenceKind,
    LocationInfo,
    NightWindow,
    ObservationStyle,
    OpticalOverrides,
)
from src.services.planning import PlanningDependencies, PlanningService


def _agent_service(*, weather_failure: bool = False):
    calls: dict[str, list[dict]] = {'search': [], 'weather': [], 'equipment': []}

    async def search_places(**kwargs):
        calls['search'].append(kwargs)
        return {
            'resource_id': 'analysis-agent-contract',
            'items': [
                {
                    'name': 'Dark Ridge',
                    'lat': 30.60,
                    'lon': 119.60,
                    'score': 86.0,
                    'bortle_class': 3,
                },
                {
                    'name': 'Lake Overlook',
                    'lat': 30.55,
                    'lon': 119.70,
                    'score': 80.0,
                    'bortle_class': 4,
                },
            ],
        }

    async def fetch_weather(**kwargs):
        calls['weather'].append(kwargs)
        if weather_failure:
            raise MCPError(MCPError.API_TIMEOUT, 'weather timed out')
        cloud_cover = 8.0 if kwargs['lat'] == 30.60 else 18.0
        return {
            'summary': {
                'current': {
                    'weather_text': 'Clear',
                    'cloud_cover_percent': cloud_cover,
                    'visibility_km': 20.0,
                    'wind_speed_kph': 6.0,
                },
                'hourly': [
                    {
                        'time': f'2026-10-{day}T{hour:02d}:00:00+08:00',
                        'cloud_cover_percent': cloud_cover,
                        'wind_speed_kph': 6.0,
                    }
                    for day in (25, 26)
                    for hour in range(24)
                ],
            }
        }

    async def fetch_forecast(**_kwargs):
        return {
            'moon_phase': {'phase_name': 'New Moon', 'illumination': 0.02},
            'planets': [{'name': 'Jupiter'}],
            'deep_sky': [{'name': 'M31', 'type': 'galaxy', 'score': 90.0}],
        }

    async def fetch_night_window(_lat, _lon, reference):
        if reference.hour < 12:
            reference -= timedelta(days=1)
        local_date = reference.date().isoformat()
        next_date = (reference.date() + timedelta(days=1)).isoformat()
        return NightWindow(
            local_date=local_date,
            civil_dusk=f'{local_date}T20:30:00+08:00',
            civil_dawn=f'{next_date}T04:30:00+08:00',
            duration_hours=8.0,
            time_zone='Asia/Shanghai',
        )

    async def resolve_place(place_name: str):
        assert place_name == '浙江省安吉县'
        return LocationInfo(name='浙江省湖州市安吉县', lat=30.63, lon=119.68)

    async def fetch_equipment_targets(**kwargs):
        calls['equipment'].append(kwargs)
        return {
            'targets': [
                {
                    'name': 'M42',
                    'type': 'nebula',
                    'suitability_score': 96.0,
                }
            ]
        }

    service = PlanningService(
        PlanningDependencies(
            search_places=search_places,
            fetch_weather=fetch_weather,
            fetch_forecast=fetch_forecast,
            fetch_night_window=fetch_night_window,
            now=lambda: datetime(2026, 10, 24, 9, 0, tzinfo=UTC),
            resolve_place=resolve_place,
            fetch_equipment_targets=fetch_equipment_targets,
        )
    )
    return service, calls


@pytest.mark.asyncio
async def test_best_plan_uses_recall_pool_before_candidate_limit():
    """A weather winner outside the static top-N can overturn the first ranking."""
    search_calls: list[dict] = []
    weather_calls: list[dict] = []
    forecast_calls: list[dict] = []
    night_window_calls: list[dict] = []
    locations = [
        {
            'name': 'Static Leader',
            'lat': 30.60,
            'lon': 119.60,
            'score': 96.0,
            'bortle_class': 3,
        },
        {
            'name': 'Static Runner',
            'lat': 30.70,
            'lon': 119.70,
            'score': 88.0,
            'bortle_class': 3,
        },
        {
            'name': 'Static Third',
            'lat': 30.80,
            'lon': 119.80,
            'score': 82.0,
            'bortle_class': 4,
        },
        {
            'name': 'Clear Plateau',
            'lat': 30.90,
            'lon': 119.90,
            'score': 72.0,
            'bortle_class': 4,
        },
    ]

    async def search_places(**kwargs):
        search_calls.append(kwargs)
        return {'resource_id': 'recall-regression', 'items': locations}

    async def fetch_weather(**kwargs):
        weather_calls.append(kwargs)
        weather = {
            30.60: (90.0, 4.0),
            30.70: (80.0, 5.0),
            30.80: (70.0, 10.0),
            30.90: (0.0, 25.0),
        }[round(float(kwargs['lat']), 2)]
        return {
            'summary': {
                'current': {
                    'weather_text': 'Clear' if weather[0] == 0 else 'Cloudy',
                    'cloud_cover_percent': weather[0],
                    'visibility_km': weather[1],
                    'wind_speed_kph': 5.0,
                },
                'hourly': [
                    {
                        'time': '2026-10-25T21:00:00+08:00',
                        'cloud_cover_percent': weather[0],
                        'visibility_km': weather[1],
                        'wind_speed_kph': 5.0,
                    }
                ],
            }
        }

    async def fetch_forecast(**_kwargs):
        forecast_calls.append(_kwargs)
        return {
            'moon_phase': {'phase_name': 'New Moon', 'illumination': 0.02},
            'planets': [{'name': 'Jupiter'}],
            'deep_sky': [{'name': 'M31', 'type': 'galaxy', 'score': 90.0}],
        }

    async def fetch_night_window(_lat, _lon, reference):
        night_window_calls.append({'lat': _lat, 'lon': _lon})
        local_date = reference.date().isoformat()
        next_date = (reference.date() + timedelta(days=1)).isoformat()
        return NightWindow(
            local_date=local_date,
            civil_dusk=f'{local_date}T20:00:00+08:00',
            civil_dawn=f'{next_date}T04:00:00+08:00',
            duration_hours=8.0,
            time_zone='Asia/Shanghai',
        )

    service = PlanningService(
        PlanningDependencies(
            search_places=search_places,
            fetch_weather=fetch_weather,
            fetch_forecast=fetch_forecast,
            fetch_night_window=fetch_night_window,
            now=lambda: datetime(2026, 10, 25, 9, 0, tzinfo=UTC),
        )
    )

    result = await service.build_best_plan(
        south=30.5,
        west=119.5,
        north=31.0,
        east=120.0,
        time='2026-10-25 20:00:00',
        time_zone='Asia/Shanghai',
        candidate_limit=1,
        max_locations=4,
    )

    assert result.summary.total_candidates == 1
    assert result.candidates[0].location.name == 'Clear Plateau'
    assert result.candidates[0].rank == 1
    assert search_calls[0]['page_size'] == 4
    assert len(weather_calls) == 4
    assert len(forecast_calls) == 3
    assert len(night_window_calls) == 3


@pytest.mark.asyncio
async def test_agent_plan_resolves_place_and_returns_auditable_decision():
    service, calls = _agent_service()
    request = AgentPlanningRequest(
        location=AgentLocationIntent(place_name=' 浙江省安吉县 ', radius_km=40),
        start_date='2026-10-25',
        nights=1,
        observation_style=ObservationStyle.DEEP_SKY,
        equipment=AgentEquipmentIntent(
            preset=EquipmentPreset.SEESTAR_S50,
            overrides=OpticalOverrides(focal_length_mm=260),
        ),
        candidate_limit=2,
    )

    result = await service.build_agent_plan(request)

    assert result.request.time_zone == 'Asia/Shanghai'
    assert result.request.target_limit == 5
    assert result.resolved_location.input_mode == 'place_name'
    assert result.resolved_location.display_name == '浙江省湖州市安吉县'
    assert result.decision is not None
    assert result.decision.location.name == 'Dark Ridge'
    assert result.decision.score_breakdown.final_score == result.decision.recommendation_score
    assert result.decision.targets[0].name == 'M42'
    assert result.decision.equipment is not None
    assert result.decision.equipment.focal_length_mm == 260
    assert result.decision.equipment.aperture_mm == 50
    assert len(result.alternatives) == 1
    assert result.alternatives[0].score_difference > 0
    assert set(result.alternatives[0].comparison) == {
        'place_contribution',
        'weather_contribution',
        'popularity_adjustment',
        'accessibility_adjustment',
    }
    assert {item.kind for item in result.evidence} == {
        EvidenceKind.PLACE,
        EvidenceKind.WEATHER,
        EvidenceKind.SKY,
        EvidenceKind.EQUIPMENT,
    }
    assert result.missing_inputs == []
    assert {item.factor for item in result.would_change_if} >= {'weather', 'score_gap'}
    assert {item.action for item in result.next_actions} >= {'recheck_weather', 'confirm_access'}

    assert calls['search'][0]['db_config_path'] is None
    assert all(call['provider'] == 'all' for call in calls['weather'])
    assert calls['equipment'][0]['focal_length_mm'] == 260
    assert calls['equipment'][0]['mount_type'] == 'altaz'
    assert calls['equipment'][0]['filter_type'] is None


@pytest.mark.asyncio
async def test_agent_plan_surfaces_missing_equipment_and_weather_degradation():
    service, _calls = _agent_service(weather_failure=True)
    request = AgentPlanningRequest(
        location=AgentLocationIntent(place_name='浙江省安吉县'),
        start_date='2026-10-25',
        nights=1,
        observation_style=ObservationStyle.DEEP_SKY,
        candidate_limit=1,
    )

    result = await service.build_agent_plan(request)

    assert result.decision is None
    assert result.alternatives == []
    assert [item.field for item in result.missing_inputs] == ['equipment']
    assert {item.code for item in result.uncertainties} >= {
        'nightly_weather_unavailable',
        'no_recommendable_session',
    }
    assert {item.action for item in result.next_actions} >= {'provide_equipment', 'recheck_weather'}
    references = [item for item in result.evidence if item.source == 'unranked_planning_reference']
    assert references
    assert references[0].facts['status'] == 'weather_unknown'
    assert references[0].facts['targets']


@pytest.mark.asyncio
async def test_agent_plan_resolves_hope_d60_asi2600mc_air_preset_and_overrides():
    service, calls = _agent_service()
    request = AgentPlanningRequest(
        location=AgentLocationIntent(center={'lat': 30.63, 'lon': 119.68}),
        start_date='2026-10-25',
        nights=1,
        observation_style=ObservationStyle.DEEP_SKY,
        equipment=AgentEquipmentIntent(
            preset=EquipmentPreset.HOPE_D60_ASI2600MC_AIR,
            overrides=OpticalOverrides(filter_type='dual_narrowband'),
        ),
        candidate_limit=1,
    )

    result = await service.build_agent_plan(request)

    assert result.decision is not None
    assert result.decision.equipment is not None
    assert result.decision.equipment.model_dump(mode='json') == {
        'preset': 'hope_d60_asi2600mc_air',
        'focal_length_mm': 280.0,
        'aperture_mm': 60.0,
        'sensor_width_mm': 23.5,
        'sensor_height_mm': 15.7,
        'sensor_pixel_size_um': 3.76,
        'central_obstruction_pct': 0,
        'reducer_factor': 1.0,
        'barlow_factor': 1.0,
        'mount_type': 'equatorial',
        'filter_type': 'dual_narrowband',
    }
    assert calls['equipment'][0] == {
        'focal_length_mm': 280.0,
        'aperture_mm': 60.0,
        'sensor_width_mm': 23.5,
        'sensor_height_mm': 15.7,
        'sensor_pixel_size_um': 3.76,
        'central_obstruction_pct': 0,
        'reducer_factor': 1.0,
        'barlow_factor': 1.0,
        'mount_type': 'equatorial',
        'filter_type': 'dual_narrowband',
        'lon': 119.6,
        'lat': 30.6,
        'time': '2026-10-26 00:30:00',
        'time_zone': 'Asia/Shanghai',
        'limit': 5,
    }


def test_agent_request_schema_hides_server_infrastructure_and_echoes_defaults():
    schema = AgentPlanningRequest.model_json_schema()
    properties = schema['properties']

    assert 'weather_provider' not in properties
    assert 'db_config_path' not in properties
    request = AgentPlanningRequest(
        location=AgentLocationIntent(center={'lat': 30.63, 'lon': 119.68}),
        start_date='2026-10-25',
    )
    assert request.model_dump(mode='json')['nights'] == 3
    assert request.model_dump(mode='json')['candidate_limit'] == 3
    assert request.model_dump(mode='json')['observation_style'] == 'balanced'


def test_agent_request_rejects_ambiguous_location_and_incomplete_custom_equipment():
    with pytest.raises(ValidationError, match='exactly one'):
        AgentLocationIntent(
            place_name='浙江省安吉县',
            center={'lat': 30.63, 'lon': 119.68},
        )

    with pytest.raises(ValidationError, match='focal_length_mm'):
        AgentEquipmentIntent(preset=EquipmentPreset.CUSTOM)


@pytest.mark.asyncio
@pytest.mark.parametrize('unavailable', ['unknown', 'rain'])
async def test_reference_with_high_place_score_cannot_displace_usable_session(unavailable):
    from dataclasses import replace

    service, _calls = _agent_service()
    original_weather = service._dependencies.fetch_weather
    original_places = service._dependencies.search_places

    async def places(**kwargs):
        result = await original_places(**kwargs)
        result['items'][0]['score'] = 100
        result['items'][1]['score'] = 1
        return result

    async def weather(**kwargs):
        result = await original_weather(**kwargs)
        if kwargs['lat'] == 30.60:
            if unavailable == 'unknown':
                result['summary']['hourly'] = []
            else:
                for hour in result['summary']['hourly']:
                    hour['precipitation_probability'] = 1.0
        return result

    service._dependencies = replace(
        service._dependencies, fetch_weather=weather, search_places=places
    )
    request = AgentPlanningRequest(
        location=AgentLocationIntent(center={'lat': 30.63, 'lon': 119.68}),
        start_date='2026-10-25',
        nights=1,
        candidate_limit=2,
    )
    result = await service.build_agent_plan(request)
    assert result.decision.location.name == 'Lake Overlook'
    assert result.alternatives == []
    reference = next(e for e in result.evidence if e.source == 'unranked_planning_reference')
    assert reference.facts['location']['name'] == 'Dark Ridge'
    assert reference.facts['status'] == (
        'weather_unknown' if unavailable == 'unknown' else 'no_usable_window'
    )
    # The same eligibility gate must also protect the historical multiday summary.
    multi = await service.build_multiday_plan(
        south=30,
        west=119,
        north=31,
        east=120,
        start_date='2026-10-25',
        time_zone='Asia/Shanghai',
        nights=1,
        candidate_limit=2,
    )
    assert multi.summary.best_location_name == 'Lake Overlook'


@pytest.mark.asyncio
async def test_all_unknown_nights_have_no_best_night_but_keep_references():
    service, _calls = _agent_service(weather_failure=True)
    multi = await service.build_multiday_plan(
        south=30,
        west=119,
        north=31,
        east=120,
        start_date='2026-10-25',
        time_zone='Asia/Shanghai',
        nights=2,
    )
    assert multi.summary.best_night_date is None
    assert multi.summary.best_night_index is None
    assert multi.summary.best_score is None
    assert all(n.plan.summary.recommended_location_name is None for n in multi.nights)
    assert all(n.plan.candidates[0].top_targets for n in multi.nights)


@pytest.mark.asyncio
@pytest.mark.parametrize('weather_failure', [True, False])
async def test_sdk_planner_obeys_weather_eligibility_gate(monkeypatch, weather_failure):
    from fastmcp import Client

    from src.functions.planning import agent_impl
    from src.server_instance import mcp

    service, _calls = _agent_service(weather_failure=weather_failure)
    monkeypatch.setattr(agent_impl, '_build_planning_service', lambda: service)
    request = {
        'location': {'center': {'lat': 30.63, 'lon': 119.68}},
        'start_date': '2026-10-25',
        'nights': 1,
    }
    async with Client(mcp._mcp) as client:
        result = await client.call_tool('plan_stargazing_session', {'request': request})
    payload = result.structured_content
    assert payload['_meta']['status'] == 'success'
    if weather_failure:
        assert payload['data']['decision'] is None
        assert payload['data']['alternatives'] == []
        assert any(
            e['source'] == 'unranked_planning_reference' for e in payload['data']['evidence']
        )
    else:
        assert payload['data']['decision']['observation_window'] is not None
