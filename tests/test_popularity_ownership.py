"""Planning uses a neutral SPF baseline even when a preferred search is cached."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import src.functions.places.impl as places
import src.placefinder as bridge
from src.analysis_cache import AnalysisCache
from src.functions.planning.impl import _search_places
from src.schemas import AgentPlanningRequest, NightWindow
from src.services.planning import PlanningDependencies, PlanningService


@pytest.mark.asyncio
@pytest.mark.parametrize('entrypoint', ['single', 'multiday', 'agent'])
@pytest.mark.parametrize(
    'avoid,quiet,has_signals',
    [
        (False, False, True),
        (True, False, True),
        (False, True, True),
        (True, True, True),
        (True, True, False),
    ],
)
async def test_popularity_is_applied_once_across_planning_entrypoints(
    monkeypatch, entrypoint, avoid, quiet, has_signals
):
    # Model a provider that changes its returned score when preferences are
    # enabled. A fixed mock response would hide the original double counting.
    def analyze_area(**kwargs):
        adjusted = kwargs['avoid_popular_spots'] or kwargs['prefer_quiet_at_night']
        return [
            {
                'name': name,
                'lat': lat,
                'lon': 116.1,
                'stargazing_score': base - 25.0 if adjusted else base,
                'static_popularity_risk_score': risk if has_signals else None,
                'night_quiet_likelihood_score': night_quiet if has_signals else None,
                'temporal_popularity_confidence': 100.0,
            }
            for name, lat, base, risk, night_quiet in [
                ('Popular Ridge', 40.1, 70.0, 80.0, 20.0),
                ('Quiet Ridge', 40.2, 68.0, 20.0, 80.0),
            ]
        ]

    provider = SimpleNamespace(
        init_stargazing_analyzer=MagicMock(), analyze_area=MagicMock(side_effect=analyze_area)
    )
    monkeypatch.setattr(bridge, '_load_spf', lambda: provider)
    monkeypatch.setattr(bridge, '_load_spf_config', lambda: None)
    monkeypatch.setattr(bridge, '_last_params', None)
    monkeypatch.setattr(places, 'ANALYSIS_CACHE', AnalysisCache())

    async def night_window(_lat, _lon, reference):
        dusk = reference.replace(hour=20, minute=0, second=0)
        dawn = (dusk + timedelta(days=1)).replace(hour=4)
        return NightWindow(
            local_date=dusk.date().isoformat(),
            civil_dusk=dusk.isoformat(),
            civil_dawn=dawn.isoformat(),
            duration_hours=8.0,
            time_zone='Asia/Shanghai',
        )

    service = PlanningService(
        PlanningDependencies(
            search_places=_search_places,
            fetch_weather=AsyncMock(
                return_value={'summary': {'current': {'cloud_cover_percent': 50.0}, 'hourly': []}}
            ),
            fetch_forecast=AsyncMock(return_value={}),
            fetch_night_window=night_window,
            now=lambda: datetime(2026, 10, 26, tzinfo=UTC),
        )
    )
    bounds = dict(south=40.0, west=116.0, north=40.5, east=116.5)
    search = dict(**bounds, max_locations=10, page_size=10, popularity_radius_km=4.5)

    # Exercise the public area tool first: it must still forward preferences,
    # and its adjusted cache entry must never feed the composite planner.
    direct = await places.analysis_area.fn(
        **search, avoid_popular_spots=True, prefer_quiet_at_night=True
    )
    assert direct['data']['items'][0]['score'] == 45.0
    assert provider.analyze_area.call_args.kwargs['avoid_popular_spots'] is True
    assert provider.analyze_area.call_args.kwargs['prefer_quiet_at_night'] is True

    preferences = dict(
        avoid_popular_spots=avoid, prefer_quiet_at_night=quiet, popularity_radius_km=4.5
    )
    if entrypoint == 'single':
        plan = await service.build_best_plan(
            **bounds, **preferences, time='2026-10-27 22:00:00', time_zone='Asia/Shanghai'
        )
        scores = {item.location.name: item.score_breakdown for item in plan.candidates}
        resource_id = plan.query.analysis_resource_id
        assert plan.query.avoid_popular_spots is avoid
        assert plan.query.prefer_quiet_at_night is quiet
        winner = plan.candidates[0].location.name
    elif entrypoint == 'multiday':
        result = await service.build_multiday_plan(
            **bounds, **preferences, start_date='2026-10-27', nights=2, time_zone='Asia/Shanghai'
        )
        assert result.summary.successful_nights == 2
        plan = result.nights[0].plan
        assert all(
            first.score_breakdown == second.score_breakdown
            for first, second in zip(plan.candidates, result.nights[1].plan.candidates, strict=True)
        )
        scores = {item.location.name: item.score_breakdown for item in plan.candidates}
        resource_id = plan.query.analysis_resource_id
        assert plan.query.avoid_popular_spots is avoid
        assert plan.query.prefer_quiet_at_night is quiet
        winner = plan.candidates[0].location.name
    else:
        result = await service.build_agent_plan(
            AgentPlanningRequest(
                location={'bounds': bounds}, start_date='2026-10-27', **preferences
            )
        )
        assert result.decision is not None
        scores = {result.decision.location.name: result.decision.score_breakdown}
        scores.update({item.location.name: item.score_breakdown for item in result.alternatives})
        resource_id = next(item.resource_id for item in result.evidence if item.resource_id)
        winner = result.decision.location.name

    # Neutral results are shared across all nights; a paged neutral public
    # search reuses exactly the resource advertised by the planner.
    neutral = await places.analysis_area.fn(**{**search, 'page_size': 1}, page=2)
    assert resource_id == neutral['data']['resource_id']
    assert resource_id != direct['data']['resource_id']
    assert provider.analyze_area.call_count == 2
    assert provider.analyze_area.call_args.kwargs['avoid_popular_spots'] is False
    assert provider.analyze_area.call_args.kwargs['prefer_quiet_at_night'] is False
    assert provider.analyze_area.call_args.kwargs['popularity_radius_km'] == 4.5
    assert scores['Popular Ridge'].place_base_score == 70.0
    assert scores['Quiet Ridge'].place_base_score == 68.0
    # Each enabled preference contributes 6.3 points at a 4.5 km horizon.
    adjustment = 6.3 * (int(avoid) + int(quiet)) if has_signals else 0.0
    assert scores['Popular Ridge'].popularity_adjustment == pytest.approx(-adjustment)
    assert scores['Quiet Ridge'].popularity_adjustment == pytest.approx(adjustment)
    # Current-only weather is unknown for these future nights (neutral 55),
    # not a dated cloud-cover forecast. Popularity is still applied once.
    assert scores['Popular Ridge'].weather_base_score == 55.0
    assert scores['Popular Ridge'].final_score == pytest.approx(
        70.0 * 0.65 + 55.0 * 0.35 - adjustment
    )
    assert scores['Quiet Ridge'].final_score == pytest.approx(
        68.0 * 0.65 + 55.0 * 0.35 + adjustment
    )
    assert scores['Quiet Ridge'].factor_contributions['popularity_preferences'] == pytest.approx(
        adjustment
    )
    assert winner == ('Quiet Ridge' if adjustment else 'Popular Ridge')
