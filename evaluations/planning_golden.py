"""Frozen planning scenarios shared by contract tests and black-box clients."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from src.response import MCPError
from src.schemas import (
    AgentEquipmentIntent,
    AgentLocationIntent,
    AgentPlanningRequest,
    EquipmentPreset,
    LocationInfo,
    NightWindow,
    ObservationStyle,
)
from src.services.planning import PlanningDependencies, PlanningService


@dataclass(frozen=True)
class GoldenScenario:
    """One stable planning question and the deterministic evidence behind it."""

    scenario_id: str
    question: str
    expected_answer: str
    expected_path: str
    request: AgentPlanningRequest
    locations: tuple[dict[str, Any], ...]
    weather_by_lat: dict[float, dict[str, Any]] = field(default_factory=dict)
    equipment_targets: tuple[dict[str, Any], ...] = ()
    weather_failure: bool = False
    equipment_failure: bool = False
    night_window_failure: bool = False


def _request(
    start_date: str,
    style: ObservationStyle,
    *,
    equipment: EquipmentPreset | None = None,
    nights: int = 1,
    candidate_limit: int = 2,
) -> AgentPlanningRequest:
    equipment_intent = AgentEquipmentIntent(preset=equipment) if equipment else None
    return AgentPlanningRequest(
        location=AgentLocationIntent(place_name='浙江省安吉县', radius_km=40),
        start_date=start_date,
        nights=nights,
        observation_style=style,
        equipment=equipment_intent,
        candidate_limit=candidate_limit,
        target_limit=5,
    )


def _location(name: str, lat: float, score: float, bortle: int = 3) -> dict[str, Any]:
    return {
        'name': name,
        'lat': lat,
        'lon': 119.60 + (lat - 30.60),
        'score': score,
        'bortle_class': bortle,
        'road_distance_km': 1.0,
    }


def _weather(cloud_cover: float, visibility_km: float = 20.0) -> dict[str, Any]:
    return {
        'summary': {
            'current': {
                'weather_text': 'Clear' if cloud_cover < 30 else 'Cloudy',
                'cloud_cover_percent': cloud_cover,
                'visibility_km': visibility_km,
                'wind_speed_kph': 6.0,
            },
            'hourly': [],
        }
    }


_DARK_RIDGE = _location('Dark Ridge', 30.60, 91.0, 2)
_LAKE_OVERLOOK = _location('Lake Overlook', 30.70, 78.0, 4)
_CLEAR_PLATEAU = _location('Clear Plateau', 30.80, 74.0, 4)
_EASY_ACCESS_HILL = _location('Easy Access Hill', 30.90, 82.0, 3)


GOLDEN_SCENARIOS: tuple[GoldenScenario, ...] = (
    GoldenScenario(
        scenario_id='deep-sky-seestar-ranking',
        question=(
            'Using the frozen evaluation data, compare the available sites around Anji for '
            'deep-sky imaging on 2024-10-01 with a Seestar S50. What exact location name is the '
            'first choice?'
        ),
        expected_answer='Dark Ridge',
        expected_path='decision.location.name',
        request=_request(
            '2024-10-01', ObservationStyle.DEEP_SKY, equipment=EquipmentPreset.SEESTAR_S50
        ),
        locations=(_DARK_RIDGE, _LAKE_OVERLOOK),
        weather_by_lat={30.60: _weather(8), 30.70: _weather(25)},
        equipment_targets=({'name': 'M42', 'type': 'nebula', 'suitability_score': 94.0},),
    ),
    GoldenScenario(
        scenario_id='hope-d60-equipment-target',
        question=(
            'Using the frozen evaluation data, plan deep-sky imaging around Anji on 2024-10-02 '
            'with the HOPE D60 + ASI2600MC Air preset. What is the exact top equipment-matched '
            'target name?'
        ),
        expected_answer='M31',
        expected_path='decision.targets.0.name',
        request=_request(
            '2024-10-02',
            ObservationStyle.DEEP_SKY,
            equipment=EquipmentPreset.HOPE_D60_ASI2600MC_AIR,
            candidate_limit=1,
        ),
        locations=(_DARK_RIDGE,),
        weather_by_lat={30.60: _weather(6)},
        equipment_targets=({'name': 'M31', 'type': 'galaxy', 'suitability_score': 98.0},),
    ),
    GoldenScenario(
        scenario_id='visual-weather-ranking',
        question=(
            'Using the frozen evaluation data, compare both Anji sites for visual observing on '
            '2024-10-03. One site is darker but heavily clouded. What exact location name wins '
            'after weather is included?'
        ),
        expected_answer='Clear Plateau',
        expected_path='decision.location.name',
        request=_request('2024-10-03', ObservationStyle.VISUAL),
        locations=(_DARK_RIDGE, _CLEAR_PLATEAU),
        weather_by_lat={30.60: _weather(95, 3), 30.80: _weather(0, 25)},
    ),
    GoldenScenario(
        scenario_id='planetary-target-order',
        question=(
            'Using the frozen evaluation data, plan planetary observing around Anji on '
            '2024-10-04. What exact target name appears first?'
        ),
        expected_answer='Jupiter',
        expected_path='decision.targets.0.name',
        request=_request('2024-10-04', ObservationStyle.PLANETARY, candidate_limit=1),
        locations=(_LAKE_OVERLOOK,),
        weather_by_lat={30.70: _weather(10)},
    ),
    GoldenScenario(
        scenario_id='beginner-single-choice',
        question=(
            'Using the frozen evaluation data, make a beginner observing plan around Anji on '
            '2024-10-05. What exact location name is recommended?'
        ),
        expected_answer='Easy Access Hill',
        expected_path='decision.location.name',
        request=_request('2024-10-05', ObservationStyle.BEGINNER, candidate_limit=1),
        locations=(_EASY_ACCESS_HILL,),
        weather_by_lat={30.90: _weather(12)},
    ),
    GoldenScenario(
        scenario_id='empty-candidates-action',
        question=(
            'Using the frozen evaluation data, plan around Anji on 2024-10-06 when place search '
            'returns no candidates. What exact next-action code is returned?'
        ),
        expected_answer='expand_search_area',
        expected_path='next_actions.0.action',
        request=_request('2024-10-06', ObservationStyle.BALANCED),
        locations=(),
    ),
    GoldenScenario(
        scenario_id='weather-provider-degradation',
        question=(
            'Using the frozen evaluation data, plan around Anji on 2024-10-07 while the weather '
            'provider is unavailable. The plan must remain actionable. What exact first '
            'next-action code is returned?'
        ),
        expected_answer='recheck_weather',
        expected_path='next_actions.0.action',
        request=_request('2024-10-07', ObservationStyle.VISUAL, candidate_limit=1),
        locations=(_CLEAR_PLATEAU,),
        weather_failure=True,
    ),
    GoldenScenario(
        scenario_id='night-window-unavailable',
        question=(
            'Using the frozen evaluation data, plan around Anji on 2024-10-08 when no civil-dark '
            'window can be determined. What exact uncertainty code is returned?'
        ),
        expected_answer='no_candidates',
        expected_path='uncertainties.0.code',
        request=_request('2024-10-08', ObservationStyle.BALANCED),
        locations=(_DARK_RIDGE,),
        night_window_failure=True,
    ),
    GoldenScenario(
        scenario_id='historical-multinight',
        question=(
            'Using the frozen evaluation data, compare two historical nights starting '
            '2023-11-18 around Anji. Return the selected local date in YYYY-MM-DD format.'
        ),
        expected_answer='2023-11-18',
        expected_path='decision.date',
        request=_request('2023-11-18', ObservationStyle.DEEP_SKY, nights=2, candidate_limit=1),
        locations=(_DARK_RIDGE,),
        weather_by_lat={30.60: _weather(5)},
    ),
    GoldenScenario(
        scenario_id='equipment-matching-degradation',
        question=(
            'Using the frozen evaluation data, plan around Anji on 2024-10-10 with a Seestar S50 '
            'while equipment-specific target matching fails. What exact uncertainty code records '
            'that failure?'
        ),
        expected_answer='equipment_target_matching_failed',
        expected_path='uncertainties.0.code',
        request=_request(
            '2024-10-10',
            ObservationStyle.DEEP_SKY,
            equipment=EquipmentPreset.SEESTAR_S50,
            candidate_limit=1,
        ),
        locations=(_DARK_RIDGE,),
        weather_by_lat={30.60: _weather(7)},
        equipment_failure=True,
    ),
)

SCENARIOS_BY_DATE = {scenario.request.start_date: scenario for scenario in GOLDEN_SCENARIOS}


def build_golden_service(scenario: GoldenScenario) -> PlanningService:
    """Build a planning service backed only by one frozen scenario."""

    async def search_places(**_kwargs):
        return {
            'resource_id': f'golden-{scenario.scenario_id}',
            'items': [dict(item) for item in scenario.locations],
        }

    async def fetch_weather(**kwargs):
        if scenario.weather_failure:
            raise MCPError(MCPError.API_TIMEOUT, 'frozen weather provider timeout')
        return scenario.weather_by_lat.get(round(float(kwargs['lat']), 2), _weather(15))

    async def fetch_forecast(**_kwargs):
        return {
            'moon_phase': {'phase_name': 'New Moon', 'illumination': 0.02},
            'planets': [{'name': 'Jupiter'}],
            'deep_sky': [{'name': 'M31', 'type': 'galaxy', 'score': 91.0}],
        }

    async def fetch_night_window(_lat: float, _lon: float, reference: datetime):
        if scenario.night_window_failure:
            raise ValueError('frozen scenario has no civil-dark window')
        local_date = reference.date().isoformat()
        next_date = (reference.date() + timedelta(days=1)).isoformat()
        return NightWindow(
            local_date=local_date,
            civil_dusk=f'{local_date}T20:00:00+08:00',
            civil_dawn=f'{next_date}T04:00:00+08:00',
            duration_hours=8.0,
            time_zone='Asia/Shanghai',
        )

    async def resolve_place(place_name: str):
        return LocationInfo(name=place_name, lat=30.63, lon=119.68, timezone='Asia/Shanghai')

    async def fetch_equipment_targets(**_kwargs):
        if scenario.equipment_failure:
            raise MCPError(MCPError.EXTERNAL_API_ERROR, 'frozen equipment matcher failure')
        return {'targets': [dict(item) for item in scenario.equipment_targets]}

    return PlanningService(
        PlanningDependencies(
            search_places=search_places,
            fetch_weather=fetch_weather,
            fetch_forecast=fetch_forecast,
            fetch_night_window=fetch_night_window,
            now=lambda: datetime(2026, 10, 25, tzinfo=UTC),
            resolve_place=resolve_place,
            fetch_equipment_targets=fetch_equipment_targets,
        )
    )


def extract_result_value(result: Any, path: str) -> str:
    """Extract one directly comparable answer from a Pydantic result."""

    value = result
    for part in path.split('.'):
        if part.isdigit():
            value = value[int(part)]
        else:
            value = getattr(value, part)
    return str(value)
