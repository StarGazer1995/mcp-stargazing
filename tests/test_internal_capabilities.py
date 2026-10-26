"""Direct tests for transport-free capabilities shared by MCP and planning."""

from unittest.mock import MagicMock, patch

import pytest

from src.functions.celestial.impl import build_nightly_forecast_capability
from src.functions.places.impl import analyze_area_capability, compute_area_locations
from src.functions.weather.impl import fetch_weather_by_position_capability
from src.response import MCPError
from src.schemas import AggregatedWeatherResponse, NightWindow, StargazingLocation


@pytest.mark.parametrize('stage', ['construction', 'analysis'])
@pytest.mark.parametrize(
    ('failure', 'code'),
    [
        (ModuleNotFoundError('unavailable'), MCPError.CONFIGURATION_ERROR),
        (RuntimeError('provider failed'), MCPError.EXTERNAL_API_ERROR),
    ],
)
def test_shared_place_compute_translates_dependency_and_provider_errors(stage, failure, code):
    with patch('src.functions.places.impl.StargazingPlaceFinder') as finder:
        if stage == 'construction':
            finder.side_effect = failure
        else:
            finder.return_value.analyze_area.side_effect = failure
        with pytest.raises(MCPError) as caught:
            compute_area_locations({'south': 30, 'west': 119, 'north': 31, 'east': 120})
    assert caught.value.code == code


@pytest.mark.asyncio
async def test_place_capability_returns_typed_data_without_mcp_envelope():
    locations = [
        StargazingLocation(
            name='Capability Ridge',
            lat=30.1,
            lon=119.1,
            elevation_m=1200,
            bortle_class=3,
            road_distance_km=2.0,
        )
    ]
    with patch('src.functions.places.impl.ANALYSIS_CACHE.get', return_value=locations):
        outcome = await analyze_area_capability(
            south=30.0,
            west=119.0,
            north=31.0,
            east=120.0,
        )

    assert outcome.result.items[0].name == 'Capability Ridge'
    assert outcome.result.total == 1
    assert outcome.warnings == []


def test_weather_capability_returns_domain_model_without_mcp_envelope():
    weather = AggregatedWeatherResponse(
        location={'name': None, 'lat': 40.0, 'lon': 116.0, 'timezone': 'Asia/Shanghai'},
        summary={'current': {'cloud_cover_percent': 12.0}, 'daily': [], 'hourly': []},
        providers={},
        source={
            'query_mode': 'all',
            'successful_providers': ['open-meteo'],
            'failed_providers': [],
        },
    )
    with patch(
        'src.functions.weather.impl.get_aggregated_weather_by_position',
        return_value=weather,
    ) as mock_fetch:
        result = fetch_weather_by_position_capability(40.0, 116.0)

    assert result is weather
    mock_fetch.assert_called_once_with(40.0, 116.0, provider='all')


@pytest.mark.asyncio
async def test_forecast_capability_returns_domain_model_without_mcp_envelope():
    with (
        patch('src.functions.celestial.impl.process_location_and_time') as mock_process,
        patch(
            'src.functions.celestial.impl.calculate_civil_night_window',
            return_value=NightWindow(
                local_date='2024-06-15',
                civil_dusk='2024-06-15T20:30:00+08:00',
                civil_dawn='2024-06-16T04:30:00+08:00',
                duration_hours=8.0,
                time_zone='Asia/Shanghai',
            ),
        ),
        patch(
            'src.functions.celestial.impl.calculate_nightly_forecast',
            return_value={
                'moon_phase': {
                    'phase_name': 'New Moon',
                    'illumination': 0.02,
                    'age_days': 0.5,
                    'elongation': 5.0,
                    'earth_distance': 384400.0,
                },
                'planets': [],
                'deep_sky': [],
            },
        ),
    ):
        mock_process.return_value = (MagicMock(), MagicMock())
        forecast = await build_nightly_forecast_capability(
            lon=116.0,
            lat=40.0,
            time='2024-06-15 22:00:00',
            time_zone='Asia/Shanghai',
            limit=5,
        )

    assert forecast.moon_phase.phase_name == 'New Moon'
    assert forecast.night_window.local_date == '2024-06-15'
