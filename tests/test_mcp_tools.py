"""Tests for MCP tool wrappers not covered by other test files."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from src.functions.celestial.impl import (
    get_constellation,
    get_moon_info,
    get_nightly_forecast,
    list_visible_planets,
)
from src.functions.metadata.impl import get_tool_catalog
from src.functions.places.impl import analysis_area, light_pollution_map
from src.functions.planning.impl import get_best_stargazing_plan
from src.functions.telescope.impl import get_shooting_plan, get_telescope_targets
from src.functions.time.impl import get_local_datetime_info
from src.functions.weather.impl import get_weather_by_name, get_weather_by_position
from src.response import MCPError

EXPECTED_TOOLS = {
    'analysis_area',
    'get_celestial_pos',
    'get_celestial_rise_set',
    'get_best_stargazing_plan',
    'get_constellation',
    'get_local_datetime_info',
    'get_moon_info',
    'get_nightly_forecast',
    'get_shooting_plan',
    'get_telescope_targets',
    'get_tool_catalog',
    'get_weather_by_name',
    'get_weather_by_position',
    'light_pollution_map',
    'list_visible_planets',
}

# ---------------------------------------------------------------------------
# Planning tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_best_stargazing_plan_fn():
    """``get_best_stargazing_plan.fn`` returns ranked composite recommendations."""
    with (
        patch('src.functions.planning.impl.datetime') as mock_datetime,
        patch('src.functions.planning.impl.analysis_area') as mock_analysis_area,
        patch('src.functions.planning.impl.get_weather_by_position') as mock_weather,
        patch('src.functions.planning.impl.get_nightly_forecast') as mock_forecast,
    ):
        mock_datetime.now.return_value = datetime(2026, 6, 27, 12, 0, tzinfo=UTC)
        mock_analysis_area.fn = AsyncMock(
            return_value={
                'data': {
                    'resource_id': 'analysis-abc123',
                    'items': [
                        {
                            'name': 'Alpha Ridge',
                            'lat': 40.1,
                            'lon': 116.1,
                            'score': 88.0,
                            'bortle_class': 3,
                        },
                        {
                            'name': 'Beta Valley',
                            'lat': 40.2,
                            'lon': 116.2,
                            'score': 72.0,
                            'bortle_class': 4,
                        },
                    ],
                },
                '_meta': {'status': 'success'},
            }
        )
        mock_weather.fn = Mock(
            side_effect=lambda lat, lon, provider: {
                'data': {
                    'summary': {
                        'current': {
                            'weather_text': 'Clear' if lat == 40.1 else 'Partly cloudy',
                            'cloud_cover_percent': 12.0 if lat == 40.1 else 35.0,
                            'visibility_km': 22.0 if lat == 40.1 else 16.0,
                            'wind_speed_kph': 8.0 if lat == 40.1 else 12.0,
                        },
                        'hourly': [
                            {
                                'time': '2024-06-15T21:00:00+08:00'
                                if lat == 40.1
                                else '2024-06-15T22:00:00+08:00',
                                'cloud_cover_percent': 10.0 if lat == 40.1 else 28.0,
                                'precipitation_probability': 0.0 if lat == 40.1 else 0.1,
                                'wind_speed_kph': 7.0 if lat == 40.1 else 10.0,
                                'weather_text': 'Clear' if lat == 40.1 else 'Partly cloudy',
                            }
                        ],
                    }
                },
                '_meta': {'status': 'success'},
            }
        )
        mock_forecast.fn = AsyncMock(
            side_effect=lambda lon, lat, time, time_zone, limit: {
                'data': {
                    'moon_phase': {'phase_name': 'New Moon', 'illumination': 0.1}
                    if lat == 40.1
                    else {'phase_name': 'First Quarter', 'illumination': 0.5},
                    'planets': [{'name': 'Jupiter'}] if lat == 40.1 else [{'name': 'Mars'}],
                    'deep_sky': (
                        [
                            {'name': 'M31', 'type': 'galaxy', 'score': 91.0},
                            {'name': 'M45', 'type': 'cluster', 'score': 82.0},
                        ]
                        if lat == 40.1
                        else [{'name': 'M13', 'type': 'cluster', 'score': 78.0}]
                    ),
                },
                '_meta': {'status': 'success'},
            }
        )

        result = await get_best_stargazing_plan.fn(
            south=40.0,
            west=116.0,
            north=40.5,
            east=116.5,
            time='2024-06-15 20:00:00',
            time_zone='Asia/Shanghai',
        )

    assert result['_meta']['status'] == 'success'
    data = result['data']
    assert data['query']['analysis_resource_id'] == 'analysis-abc123'
    assert data['query']['max_locations'] == 10
    assert data['summary']['total_candidates'] == 2
    assert data['summary']['generated_at'] == '2026-06-27T12:00:00+00:00'
    assert data['summary']['recommended_location_name'] == 'Alpha Ridge'
    assert len(data['candidates']) == 2
    assert data['candidates'][0]['rank'] == 1
    assert data['candidates'][0]['location']['name'] == 'Alpha Ridge'
    assert data['candidates'][0]['top_targets'][0]['name'] == 'M31'
    assert (
        data['candidates'][0]['best_observation_window']['start_time']
        == '2024-06-15T21:00:00+08:00'
    )
    assert (
        data['candidates'][0]['recommendation_score']
        >= data['candidates'][1]['recommendation_score']
    )


@pytest.mark.asyncio
async def test_get_best_stargazing_plan_keeps_partial_results_when_weather_fails():
    """Weather failure should degrade gracefully into notes and warnings."""
    with (
        patch('src.functions.planning.impl.analysis_area') as mock_analysis_area,
        patch('src.functions.planning.impl.get_weather_by_position') as mock_weather,
        patch('src.functions.planning.impl.get_nightly_forecast') as mock_forecast,
    ):
        mock_analysis_area.fn = AsyncMock(
            return_value={
                'data': {
                    'resource_id': 'analysis-soft-failure',
                    'items': [
                        {
                            'name': 'Gamma Summit',
                            'lat': 40.3,
                            'lon': 116.3,
                            'score': 81.0,
                            'bortle_class': 2,
                        }
                    ],
                },
                '_meta': {'status': 'success'},
            }
        )
        mock_weather.fn = Mock(
            return_value={
                'error': {'code': 'EXTERNAL_API_ERROR', 'message': '天气查询失败: timeout'},
                '_meta': {'status': 'error'},
            }
        )
        mock_forecast.fn = AsyncMock(
            return_value={
                'data': {
                    'moon_phase': {'phase_name': 'New Moon', 'illumination': 0.05},
                    'planets': [{'name': 'Saturn'}],
                    'deep_sky': [{'name': 'M8', 'type': 'nebula', 'score': 70.0}],
                },
                '_meta': {'status': 'success'},
            }
        )

        result = await get_best_stargazing_plan.fn(
            south=40.0,
            west=116.0,
            north=40.5,
            east=116.5,
            time='2024-06-15 20:00:00',
            time_zone='Asia/Shanghai',
            candidate_limit=1,
        )

    assert result['_meta']['status'] == 'success'
    data = result['data']
    assert data['summary']['warnings']
    assert '天气摘要降级处理' in data['summary']['warnings'][0]
    assert data['candidates'][0]['weather_summary'] is None
    assert data['candidates'][0]['notes']
    assert data['candidates'][0]['top_targets'][0]['name'] == 'M8'


# ---------------------------------------------------------------------------
# Celestial tools
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_nightly_forecast_fn():
    """``get_nightly_forecast.fn`` returns a structured forecast response."""
    with (
        patch('src.functions.celestial.impl.calculate_nightly_forecast') as mock_calc,
        patch('src.functions.celestial.impl.process_location_and_time') as mock_proc,
    ):
        mock_proc.return_value = (MagicMock(), MagicMock())
        mock_calc.return_value = {
            'moon_phase': {
                'phase_name': 'Full Moon',
                'illumination': 0.995,
                'age_days': 14.2,
                'elongation': 175.0,
                'earth_distance': 384400.0,
            },
            'planets': [
                {
                    'name': 'Venus',
                    'altitude': 35.5,
                    'azimuth': 220.0,
                    'constellation': 'Taurus',
                }
            ],
            'deep_sky': [
                {
                    'name': 'M31',
                    'altitude': 55.0,
                    'azimuth': 180.0,
                    'magnitude': 3.4,
                    'type': 'galaxy',
                    'catalog': 'M',
                    'score': 85.0,
                }
            ],
        }

        result = await get_nightly_forecast.fn(
            lon=-74.0, lat=40.0, time='2024-06-15 22:00:00', time_zone='America/New_York'
        )

    assert result['_meta']['status'] == 'success'
    data = result['data']
    assert data['moon_phase']['phase_name'] == 'Full Moon'
    assert len(data['planets']) == 1
    assert data['planets'][0]['name'] == 'Venus'
    assert data['planets'][0]['constellation'] == 'Taurus'
    assert len(data['deep_sky']) == 1
    assert data['deep_sky'][0]['name'] == 'M31'
    assert data['deep_sky'][0]['catalog'] == 'M'


@pytest.mark.asyncio
async def test_get_constellation_fn():
    """``get_constellation.fn`` returns constellation center position."""
    with (
        patch('src.functions.celestial.impl.get_constellation_center') as mock_calc,
        patch('src.functions.celestial.impl.process_location_and_time') as mock_proc,
    ):
        mock_proc.return_value = (MagicMock(), MagicMock())
        mock_calc.return_value = {
            'name': 'Orion',
            'altitude': 42.0,
            'azimuth': 135.0,
            'ra': '05h35m',
            'dec': '-05d23m',
        }

        result = await get_constellation.fn(
            constellation_name='Orion',
            lon=-74.0,
            lat=40.0,
            time='2024-06-15 22:00:00',
            time_zone='America/New_York',
        )

    assert result['_meta']['status'] == 'success'
    data = result['data']
    assert data == {'name': 'Orion', 'altitude': 42.0, 'azimuth': 135.0}


@pytest.mark.asyncio
async def test_list_visible_planets_fn():
    """``list_visible_planets.fn`` returns a list of visible planet dicts."""
    with (
        patch('src.celestial.get_visible_planets') as mock_calc,
        patch('src.functions.celestial.impl.process_location_and_time') as mock_proc,
    ):
        mock_proc.return_value = (MagicMock(), MagicMock())
        mock_calc.return_value = [
            {
                'name': 'Mars',
                'altitude': 25.0,
                'azimuth': 90.0,
                'magnitude': -1.2,
                'constellation': 'Gemini',
            },
            {
                'name': 'Jupiter',
                'altitude': 60.0,
                'azimuth': 180.0,
                'magnitude': -2.8,
                'constellation': 'Aries',
            },
        ]

        result = await list_visible_planets.fn(
            lon=-74.0, lat=40.0, time='2024-06-15 22:00:00', time_zone='America/New_York'
        )

    assert result['_meta']['status'] == 'success'
    data = result['data']
    assert isinstance(data, list)
    assert len(data) == 2
    assert data[0]['name'] == 'Mars'
    assert data[0]['constellation'] == 'Gemini'
    assert data[1]['name'] == 'Jupiter'
    assert data[1]['constellation'] == 'Aries'


@pytest.mark.asyncio
async def test_get_moon_info_iso_format():
    """``get_moon_info.fn`` accepts ISO format time strings."""
    with patch('src.functions.celestial.impl.calculate_moon_info') as mock_calc:
        mock_calc.return_value = {
            'phase_name': 'Waxing Crescent',
            'illumination': 0.25,
            'age_days': 4.5,
            'elongation': 30.0,
            'earth_distance': 390000.0,
        }

        result = await get_moon_info.fn(time='2024-06-15T12:00:00+00:00', time_zone='UTC')

    assert result['_meta']['status'] == 'success'
    assert result['data']['phase_name'] == 'Waxing Crescent'
    assert result['data']['illumination'] == 0.25


@pytest.mark.asyncio
async def test_get_moon_info_naive_time_localizes_timezone():
    """``get_moon_info.fn`` should localize naive timestamps with the provided timezone."""
    with patch('src.functions.celestial.impl.calculate_moon_info') as mock_calc:
        mock_calc.return_value = {
            'phase_name': 'First Quarter',
            'illumination': 0.5,
            'age_days': 7.0,
            'elongation': 90.0,
            'earth_distance': 384400.0,
        }

        result = await get_moon_info.fn(time='2024-06-15 12:00:00', time_zone='UTC')

    assert result['_meta']['status'] == 'success'
    assert result['data']['phase_name'] == 'First Quarter'
    assert result['data']['illumination'] == 0.5


# ---------------------------------------------------------------------------
# Time tool
# ---------------------------------------------------------------------------


def test_get_local_datetime_info_fn():
    """``get_local_datetime_info.fn`` returns current time and timezone."""
    result = get_local_datetime_info.fn()

    assert result['_meta']['status'] == 'success'
    data = result['data']
    assert 'current_time' in data
    assert 'time_zone' in data
    # current_time should be an ISO string
    assert 'T' in data['current_time']


# ---------------------------------------------------------------------------
# Places tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_light_pollution_map_fn():
    """``light_pollution_map.fn`` returns a light pollution grid."""
    with patch('src.functions.places.impl.get_light_pollution_grid') as mock_grid:
        mock_grid.return_value = {
            'data': [
                {
                    'lat': 40.0,
                    'lon': -74.0,
                    'brightness': 1.5,
                    'bortle': 4,
                    'sqm': 20.5,
                },
                {
                    'lat': 40.01,
                    'lon': -74.01,
                    'brightness': 0.8,
                    'bortle': 2,
                    'sqm': 21.5,
                },
            ]
        }

        result = await light_pollution_map.fn(
            south=40.0, west=-74.0, north=40.01, east=-73.99, zoom=10
        )

    assert result['_meta']['status'] == 'success'
    data = result['data']
    assert len(data['grid']) == 2
    assert data['grid'][0]['bortle'] == 4
    assert data['grid'][1]['sqm'] == 21.5
    assert data['bounds'] == {'south': 40.0, 'west': -74.0, 'north': 40.01, 'east': -73.99}
    assert data['zoom'] == 10


# ---------------------------------------------------------------------------
# analysis_area data-quality warnings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analysis_area_warns_when_all_data_missing():
    """Bortle and road warnings appear when data is absent; elevation is internal-only."""
    from src.schemas.places import StargazingLocation

    locations = [
        StargazingLocation(
            name='P1',
            lat=30.1,
            lon=119.1,
            elevation_m=0,
            bortle_class=None,
            road_distance_km=None,
        ),
        StargazingLocation(
            name='P2',
            lat=30.2,
            lon=119.2,
            elevation_m=0,
            bortle_class=None,
            road_distance_km=None,
        ),
    ]

    with patch('src.functions.places.impl.ANALYSIS_CACHE.get', return_value=locations):
        result = await analysis_area.fn(
            south=30,
            west=119,
            north=31,
            east=120,
            road_radius_km=10.0,
        )

    assert result['_meta']['status'] == 'success'
    warnings = result['_meta'].get('warnings', [])
    assert any('Bortle' in w for w in warnings), f'Expected Bortle warning, got: {warnings}'
    assert any('road' in w for w in warnings), f'Expected road warning, got: {warnings}'
    # Elevation must not leak to external response
    assert not any('elevation' in w.lower() for w in warnings), f'Elevation leaked: {warnings}'


@pytest.mark.asyncio
async def test_analysis_area_no_warnings_when_data_complete():
    """No warnings when all fields have valid values."""
    from src.schemas.places import StargazingLocation

    locations = [
        StargazingLocation(
            name='P1',
            lat=30.1,
            lon=119.1,
            elevation_m=1200,
            bortle_class=2,
            road_distance_km=5.0,
        ),
    ]

    with patch('src.functions.places.impl.ANALYSIS_CACHE.get', return_value=locations):
        result = await analysis_area.fn(
            south=30,
            west=119,
            north=31,
            east=120,
            road_radius_km=10.0,
        )

    assert result['_meta']['status'] == 'success'
    warnings = result['_meta'].get('warnings', [])
    assert len(warnings) == 0, f'Unexpected warnings: {warnings}'


@pytest.mark.asyncio
async def test_analysis_area_road_skip_silences_road_warning():
    """road_radius_km=0 suppresses the road-distance warning."""
    from src.schemas.places import StargazingLocation

    locations = [
        StargazingLocation(
            name='P1',
            lat=30.1,
            lon=119.1,
            elevation_m=1200,
            bortle_class=2,
            road_distance_km=None,
        ),
    ]

    with patch('src.functions.places.impl.ANALYSIS_CACHE.get', return_value=locations):
        result = await analysis_area.fn(
            south=30,
            west=119,
            north=31,
            east=120,
            road_radius_km=0,
        )

    assert result['_meta']['status'] == 'success'
    warnings = result['_meta'].get('warnings', [])
    # When road_radius_km=0, road warning should be suppressed
    assert not any('road' in w.lower() for w in warnings), f'Road warning leaked: {warnings}'


# ---------------------------------------------------------------------------
# Telescope / shooting plan tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_shooting_plan_fn():
    """``get_shooting_plan.fn`` returns targets + moon + timed shooting slots."""
    from stargazing_core._shooting_plan import ShootingPlan

    mock_targets = [
        {
            'name': 'M 42',
            'type': 'emission nebula',
            'ra': 83.8,
            'dec': -5.4,
            'magnitude': 4.0,
            'surface_brightness': 14.5,
            'angular_size_arcmin': 66.0,
            'altitude': 45.0,
            'azimuth': 180.0,
            'dawn_altitude': 30.0,
            'fov_fill_ratio': 0.5,
            'fov_fit_score': 0.85,
            'surface_brightness_score': 0.7,
            'filter_match_score': 0.9,
            'altitude_score': 0.5,
            'suitability_score': 82.0,
            'mosaic_recommended': False,
            'catalog': 'Messier',
            'altitude_curve': [
                {'time': 1705341600, 'alt': 30.0},
                {'time': 1705342500, 'alt': 35.0},
                {'time': 1705343400, 'alt': 50.0},
                {'time': 1705344300, 'alt': 55.0},
            ],
            'observation_time': '2024-01-15T19:00:00',
            'civil_dusk': '2024-01-15T18:00:00',
            'civil_dawn': '2024-01-16T06:00:00',
        }
    ]
    mock_moon = {
        'illumination': 0.05,
        'phase': 'Waxing Crescent',
        'altitude_curve': [
            {'time': 1705341600, 'alt': 10.0},
            {'time': 1705342500, 'alt': 5.0},
            {'time': 1705343400, 'alt': 0},
            {'time': 1705344300, 'alt': -5.0},
        ],
        'always_down': False,
        'always_up': False,
        'dark_fraction': 0.8,
    }

    with patch('src.functions.telescope.impl.match_telescope_targets') as mock_match:
        mock_match.return_value = {'targets': mock_targets, 'moon': mock_moon}

        result = await get_shooting_plan.fn(
            focal_length_mm=250,
            lon=116.4,
            lat=39.9,
            time='2024-01-15T22:00:00',
            time_zone='Asia/Shanghai',
            limit=5,
        )

    assert result['_meta']['status'] == 'success'
    data = result['data']
    assert len(data['targets']) == 1
    assert data['targets'][0]['name'] == 'M 42'
    assert data['moon']['phase'] == 'Waxing Crescent'
    assert data['moon']['illumination'] == 0.05
    assert 'plan' in data
    plan = ShootingPlan(**data['plan'])
    assert len(plan.slots) >= 1
    slot = plan.slots[0]
    assert slot.target_name == 'M 42'
    assert slot.duration_min > 0
    assert slot.start_time < slot.end_time
    assert data['total'] == 1
    assert 'config' in data


# ---------------------------------------------------------------------------
# Metadata tool
# ---------------------------------------------------------------------------


def test_get_tool_catalog_fn():
    """``get_tool_catalog.fn`` returns a list of tools wrapped in the standard response."""
    result = get_tool_catalog.fn()

    assert result['_meta']['status'] == 'success'
    data = result['data']
    assert set(data) == {'tools'}
    tools = data['tools']
    assert isinstance(tools, list)
    tool_names = {t['name'] for t in tools}
    assert tool_names == EXPECTED_TOOLS

    weather_tool = next(t for t in tools if t['name'] == 'get_weather_by_name')
    assert weather_tool['description'] == '通过地点名称获取综合天气（当前 + 小时预报 + 日预报）。'
    assert any(param['name'] == 'place_name' for param in weather_tool['parameters'])
    assert any(param['name'] == 'provider' for param in weather_tool['parameters'])


# ---------------------------------------------------------------------------
# Weather tool error paths
# ---------------------------------------------------------------------------


def test_get_weather_by_name_empty_place():
    """``get_weather_by_name`` returns error for empty place_name."""
    result = get_weather_by_name.fn('')

    assert result['_meta']['status'] == 'error'
    assert result['error']['code'] == MCPError.CONFIGURATION_ERROR
    assert '不能为空' in result['error']['message']


def test_get_weather_by_name_invalid_provider():
    """``get_weather_by_name`` returns error for unsupported provider."""
    result = get_weather_by_name.fn('Beijing', provider='invalid_provider')

    assert result['_meta']['status'] == 'error'
    assert result['error']['code'] == MCPError.CONFIGURATION_ERROR
    assert 'Unsupported provider' in result['error']['message']


def test_get_weather_by_position_invalid_coords():
    """``get_weather_by_position`` returns error for invalid coordinates."""
    result = get_weather_by_position.fn(lat=91.0, lon=0.0)  # latitude > 90

    assert result['_meta']['status'] == 'error'
    assert result['error']['code'] == MCPError.INVALID_COORDINATES


def test_get_weather_by_position_invalid_provider():
    """``get_weather_by_position`` returns error for unsupported provider."""
    result = get_weather_by_position.fn(lat=40.0, lon=116.0, provider='unknown')

    assert result['_meta']['status'] == 'error'
    assert result['error']['code'] == MCPError.CONFIGURATION_ERROR


@patch('src.functions.weather.impl.get_aggregated_weather_by_name')
def test_get_weather_by_name_generic_exception(mock_service):
    """``get_weather_by_name`` catches generic Exception and returns error response."""
    mock_service.side_effect = RuntimeError('Something unexpected')

    result = get_weather_by_name.fn('Beijing')

    assert result['_meta']['status'] == 'error'
    assert result['error']['code'] == MCPError.EXTERNAL_API_ERROR
    assert '天气查询失败' in result['error']['message']


@patch('src.functions.weather.impl.get_aggregated_weather_by_position')
def test_get_weather_by_position_generic_exception(mock_service):
    """``get_weather_by_position`` catches generic Exception and returns error response."""
    mock_service.side_effect = RuntimeError('Boom')

    result = get_weather_by_position.fn(lat=40.0, lon=116.0)

    assert result['_meta']['status'] == 'error'
    assert result['error']['code'] == MCPError.EXTERNAL_API_ERROR
    assert '天气查询失败' in result['error']['message']


# ---------------------------------------------------------------------------
# Telescope targets tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_telescope_targets_fn():
    """``get_telescope_targets.fn`` returns ranked targets for a telescope config."""
    mock_targets = [
        {
            'name': 'M 42',
            'type': 'emission nebula',
            'ra': 83.8,
            'dec': -5.4,
            'magnitude': 4.0,
            'surface_brightness': 14.5,
            'angular_size_arcmin': 66.0,
            'altitude': 45.0,
            'azimuth': 180.0,
            'fov_fill_ratio': 0.5,
            'fov_fit_score': 0.85,
            'surface_brightness_score': 0.7,
            'filter_match_score': 0.9,
            'altitude_score': 0.5,
            'suitability_score': 82.0,
            'mosaic_recommended': False,
            'catalog': 'Messier',
            'observation_time': '2024-01-15T19:00:00',
            'civil_dusk': '2024-01-15T18:00:00',
            'civil_dawn': '2024-01-16T06:00:00',
        },
        {
            'name': 'M 31',
            'type': 'spiral galaxy',
            'ra': 10.68,
            'dec': 41.27,
            'magnitude': 3.4,
            'surface_brightness': 22.3,
            'angular_size_arcmin': 189.0,
            'altitude': 60.0,
            'azimuth': 250.0,
            'fov_fill_ratio': 0.9,
            'fov_fit_score': 0.6,
            'surface_brightness_score': 0.3,
            'filter_match_score': 1.0,
            'altitude_score': 0.7,
            'suitability_score': 72.0,
            'mosaic_recommended': True,
            'catalog': 'Messier',
            'observation_time': '2024-01-15T19:00:00',
            'civil_dusk': '2024-01-15T18:00:00',
            'civil_dawn': '2024-01-16T06:00:00',
        },
    ]
    mock_moon = {
        'illumination': 0.05,
        'phase': 'Waxing Crescent',
        'always_down': False,
        'always_up': False,
    }

    with patch('src.functions.telescope.impl.match_telescope_targets') as mock_match:
        mock_match.return_value = {'targets': mock_targets, 'moon': mock_moon}

        result = await get_telescope_targets.fn(
            focal_length_mm=250,
            lon=116.4,
            lat=39.9,
            time='2024-01-15T22:00:00',
            time_zone='Asia/Shanghai',
            aperture_mm=51,
            mount_type='equatorial',
            limit=5,
        )

    assert result['_meta']['status'] == 'success'
    data = result['data']
    assert len(data['targets']) == 2
    assert data['targets'][0]['name'] == 'M 42'
    assert data['targets'][0]['suitability_score'] == 82.0
    assert data['targets'][1]['name'] == 'M 31'
    assert data['targets'][1]['mosaic_recommended'] is True
    assert data['moon']['phase'] == 'Waxing Crescent'
    assert data['moon']['illumination'] == 0.05
    assert data['total'] == 2
    assert 'config' in data
    assert data['config']['focal_length_mm'] == 250
    assert data['config']['aperture_mm'] == 51


@pytest.mark.asyncio
async def test_get_telescope_targets_with_filter():
    """``get_telescope_targets.fn`` passes filter_type through to config."""
    mock_targets = [
        {
            'name': 'NGC 7000',
            'type': 'emission nebula',
            'ra': 314.7,
            'dec': 44.3,
            'magnitude': 4.0,
            'surface_brightness': 14.0,
            'angular_size_arcmin': 120.0,
            'altitude': 50.0,
            'azimuth': 90.0,
            'fov_fill_ratio': 0.8,
            'fov_fit_score': 0.9,
            'surface_brightness_score': 0.8,
            'filter_match_score': 1.0,
            'altitude_score': 0.6,
            'suitability_score': 90.0,
            'mosaic_recommended': True,
            'catalog': 'NGC',
            'observation_time': '2024-06-15T22:00:00',
            'civil_dusk': '2024-06-15T21:00:00',
            'civil_dawn': '2024-06-16T04:00:00',
        }
    ]
    mock_moon = {
        'illumination': 0.8,
        'phase': 'Waxing Gibbous',
        'always_down': False,
        'always_up': False,
    }

    with patch('src.functions.telescope.impl.match_telescope_targets') as mock_match:
        mock_match.return_value = {'targets': mock_targets, 'moon': mock_moon}

        result = await get_telescope_targets.fn(
            focal_length_mm=250,
            lon=116.4,
            lat=39.9,
            time='2024-06-15T22:00:00',
            time_zone='Asia/Shanghai',
            filter_type='Hα',
            limit=10,
        )

    assert result['_meta']['status'] == 'success'
    data = result['data']
    assert data['targets'][0]['name'] == 'NGC 7000'
    assert data['moon']['illumination'] == 0.8
    assert data['config']['filter_type'] == 'Hα'


# ---------------------------------------------------------------------------
# Shooting plan edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_shooting_plan_uses_telescope_presets():
    """``get_shooting_plan.fn`` works with full telescope + sensor config."""
    mock_targets = [
        {
            'name': 'M 42',
            'type': 'emission nebula',
            'ra': 83.8,
            'dec': -5.4,
            'magnitude': 4.0,
            'surface_brightness': 14.5,
            'angular_size_arcmin': 66.0,
            'altitude': 55.0,
            'azimuth': 180.0,
            'dawn_altitude': 40.0,
            'fov_fill_ratio': 0.5,
            'fov_fit_score': 0.85,
            'surface_brightness_score': 0.7,
            'filter_match_score': 0.9,
            'altitude_score': 0.5,
            'suitability_score': 85.0,
            'mosaic_recommended': False,
            'catalog': 'Messier',
            'altitude_curve': [
                {'time': 1705341600, 'alt': 30.0},
                {'time': 1705342500, 'alt': 40.0},
                {'time': 1705343400, 'alt': 50.0},
                {'time': 1705344300, 'alt': 55.0},
                {'time': 1705345200, 'alt': 50.0},
                {'time': 1705346100, 'alt': 35.0},
            ],
            'observation_time': '2024-01-15T19:00:00',
            'civil_dusk': '2024-01-15T18:00:00',
            'civil_dawn': '2024-01-16T06:00:00',
        }
    ]
    mock_moon = {
        'illumination': 0.95,
        'phase': 'Full Moon',
        'altitude_curve': [
            {'time': 1705341600, 'alt': 10.0},
            {'time': 1705342500, 'alt': 20.0},
            {'time': 1705343400, 'alt': 30.0},
            {'time': 1705344300, 'alt': 40.0},
        ],
        'always_down': False,
        'always_up': False,
        'dark_fraction': 0.3,
    }

    with patch('src.functions.telescope.impl.match_telescope_targets') as mock_match:
        mock_match.return_value = {'targets': mock_targets, 'moon': mock_moon}

        result = await get_shooting_plan.fn(
            focal_length_mm=420,
            lon=-117.0,
            lat=33.0,
            time='2024-01-15T22:00:00',
            time_zone='America/Los_Angeles',
            aperture_mm=100,
            sensor_width_mm=23.5,
            sensor_height_mm=15.7,
            sensor_pixel_size_um=3.76,
            min_altitude=30.0,
            limit=5,
        )

    assert result['_meta']['status'] == 'success'
    data = result['data']
    assert len(data['targets']) == 1
    assert data['targets'][0]['name'] == 'M 42'
    assert data['moon']['phase'] == 'Full Moon'
    assert data['moon']['illumination'] == 0.95
    assert data['config']['focal_length_mm'] == 420
    assert data['config']['aperture_mm'] == 100
    assert data['config']['sensor_width_mm'] == 23.5
    assert 'plan' in data
    from stargazing_core._shooting_plan import ShootingPlan

    plan = ShootingPlan(**data['plan'])
    assert len(plan.slots) >= 1


@pytest.mark.asyncio
async def test_get_shooting_plan_empty_targets():
    """``get_shooting_plan.fn`` handles empty targets gracefully."""
    mock_moon = {
        'illumination': 0.5,
        'phase': 'First Quarter',
        'altitude_curve': [],
        'always_down': False,
        'always_up': False,
        'dark_fraction': 0.5,
    }

    with patch('src.functions.telescope.impl.match_telescope_targets') as mock_match:
        mock_match.return_value = {'targets': [], 'moon': mock_moon}

        result = await get_shooting_plan.fn(
            focal_length_mm=250,
            lon=116.4,
            lat=39.9,
            time='2024-01-15T22:00:00',
            time_zone='Asia/Shanghai',
            limit=5,
        )

    assert result['_meta']['status'] == 'success'
    data = result['data']
    assert len(data['targets']) == 0
    assert data['total'] == 0
    assert 'plan' in data
    from stargazing_core._shooting_plan import ShootingPlan

    plan = ShootingPlan(**data['plan'])
    assert len(plan.slots) == 0


# ---------------------------------------------------------------------------
# Celestial position / rise-set fn tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_celestial_pos_fn():
    """``get_celestial_pos.fn`` returns altitude/azimuth for a celestial object."""
    from src.functions.celestial.impl import get_celestial_pos

    with (
        patch('src.functions.celestial.impl.celestial_pos') as mock_calc,
        patch('src.functions.celestial.impl.process_location_and_time') as mock_proc,
    ):
        mock_proc.return_value = (MagicMock(), MagicMock())
        mock_calc.return_value = (45.5, 180.0)

        result = await get_celestial_pos.fn(
            celestial_object='M31',
            lon=-74.0,
            lat=40.0,
            time='2024-06-15 22:00:00',
            time_zone='America/New_York',
        )

    assert result['_meta']['status'] == 'success'
    data = result['data']
    assert data['altitude'] == 45.5
    assert data['azimuth'] == 180.0


@pytest.mark.asyncio
async def test_get_celestial_rise_set_fn():
    """``get_celestial_rise_set.fn`` returns rise/set times."""
    from src.functions.celestial.impl import get_celestial_rise_set

    with (
        patch('src.functions.celestial.impl.celestial_rise_set') as mock_calc,
        patch('src.functions.celestial.impl.process_location_and_time') as mock_proc,
    ):
        from datetime import UTC, datetime

        mock_proc.return_value = (MagicMock(), MagicMock())
        # celestial_rise_set returns (rise_time, set_time) as two astropy Time objects
        mock_calc.return_value = (
            datetime(2024, 6, 15, 5, 30, tzinfo=UTC),
            datetime(2024, 6, 15, 20, 15, tzinfo=UTC),
        )

        result = await get_celestial_rise_set.fn(
            celestial_object='Sun',
            lon=-74.0,
            lat=40.0,
            time='2024-06-15 22:00:00',
            time_zone='America/New_York',
        )

    assert result['_meta']['status'] == 'success'
    data = result['data']
    assert data['rise_time'] is not None
    assert data['set_time'] is not None


# ---------------------------------------------------------------------------
# Telescope — error paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_telescope_targets_invalid_coords():
    """``get_telescope_targets.fn`` returns structured error for out-of-range coordinates."""
    result = await get_telescope_targets.fn(
        focal_length_mm=250,
        lon=0.0,
        lat=95.0,  # invalid latitude > 90
        time='2024-01-15T22:00:00',
        time_zone='Asia/Shanghai',
    )
    assert result['_meta']['status'] == 'error'
    assert result['error']['code'] == MCPError.INVALID_COORDINATES


@pytest.mark.asyncio
async def test_get_telescope_targets_invalid_time():
    """``get_telescope_targets.fn`` returns structured error for invalid time format."""
    result = await get_telescope_targets.fn(
        focal_length_mm=250,
        lon=116.4,
        lat=39.9,
        time='not-a-valid-time',
        time_zone='Asia/Shanghai',
    )

    assert result['_meta']['status'] == 'error'
    assert result['error']['code'] == MCPError.INVALID_TIME_FORMAT


@pytest.mark.asyncio
async def test_get_telescope_targets_invalid_timezone():
    """``get_telescope_targets.fn`` returns structured error for invalid timezone."""
    result = await get_telescope_targets.fn(
        focal_length_mm=250,
        lon=116.4,
        lat=39.9,
        time='2024-01-15T22:00:00',
        time_zone='Not/A_Timezone',
    )

    assert result['_meta']['status'] == 'error'
    assert result['error']['code'] == MCPError.INVALID_TIMEZONE


# ---------------------------------------------------------------------------
# Shooting plan — error paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_shooting_plan_invalid_coords():
    """``get_shooting_plan.fn`` raises TypeError for out-of-range coordinates.

    Same as ``get_telescope_targets`` — the internal ``EarthLocation``
    construction throws ``TypeError`` when lat exceeds ±90°.
    """
    with pytest.raises(TypeError, match='Coordinates could not be parsed'):
        await get_shooting_plan.fn(
            focal_length_mm=250,
            lon=116.4,
            lat=95.0,  # invalid latitude > 90
            time='2024-01-15T22:00:00',
            time_zone='Asia/Shanghai',
        )


@pytest.mark.asyncio
async def test_get_shooting_plan_invalid_timezone():
    """``get_shooting_plan.fn`` raises UnknownTimeZoneError for invalid timezone."""
    import pytz

    with pytest.raises(pytz.exceptions.UnknownTimeZoneError):
        await get_shooting_plan.fn(
            focal_length_mm=250,
            lon=116.4,
            lat=39.9,
            time='2024-01-15T22:00:00',
            time_zone='Invalid/Zone',
        )


# ---------------------------------------------------------------------------
# Constellation — error paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_constellation_invalid_coords():
    """``get_constellation.fn`` returns structured error for out-of-range coordinates."""
    result = await get_constellation.fn(
        constellation_name='Orion',
        lon=-200.0,  # invalid
        lat=40.0,
        time='2024-06-15 22:00:00',
        time_zone='America/New_York',
    )

    assert result['_meta']['status'] == 'error'
    assert result['error']['code'] == MCPError.INVALID_COORDINATES


# ---------------------------------------------------------------------------
# Moon info — edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_moon_info_lat_without_lon():
    """``get_moon_info.fn`` with only lat (no lon) — no local alt/az computed."""
    with patch('src.functions.celestial.impl.calculate_moon_info') as mock_calc:
        mock_calc.return_value = {
            'phase_name': 'Waxing Crescent',
            'illumination': 0.3,
            'age_days': 5.2,
            'elongation': 45.0,
            'earth_distance': 390000.0,
        }

        result = await get_moon_info.fn(
            time='2024-06-15T12:00:00+00:00',
            time_zone='UTC',
            lat=40.0,
        )

    assert result['_meta']['status'] == 'success'
    data = result['data']
    assert data['phase_name'] == 'Waxing Crescent'
    assert data['illumination'] == 0.3


@pytest.mark.asyncio
async def test_get_moon_info_lon_without_lat():
    """``get_moon_info.fn`` with only lon (no lat) — no local alt/az computed."""
    with patch('src.functions.celestial.impl.calculate_moon_info') as mock_calc:
        mock_calc.return_value = {
            'phase_name': 'Full Moon',
            'illumination': 0.99,
            'age_days': 14.5,
            'elongation': 180.0,
            'earth_distance': 384400.0,
        }

        result = await get_moon_info.fn(
            time='2024-06-15T12:00:00+00:00',
            time_zone='UTC',
            lon=-74.0,
        )

    assert result['_meta']['status'] == 'success'
    data = result['data']
    assert data['phase_name'] == 'Full Moon'


@pytest.mark.asyncio
async def test_get_moon_info_no_position():
    """``get_moon_info.fn`` without lat/lon — only phase data returned."""
    with patch('src.functions.celestial.impl.calculate_moon_info') as mock_calc:
        mock_calc.return_value = {
            'phase_name': 'New Moon',
            'illumination': 0.01,
            'age_days': 0.5,
            'elongation': 5.0,
            'earth_distance': 405000.0,
        }

        result = await get_moon_info.fn(time='2024-06-15T12:00:00+00:00', time_zone='UTC')

    assert result['_meta']['status'] == 'success'
    data = result['data']
    assert data['phase_name'] == 'New Moon'
    assert data['altitude'] is None
    assert data['azimuth'] is None


@pytest.mark.asyncio
async def test_get_moon_info_invalid_timezone():
    """``get_moon_info.fn`` returns structured error for invalid timezone."""
    result = await get_moon_info.fn(time='2024-06-15 12:00:00', time_zone='Bad/Zone')

    assert result['_meta']['status'] == 'error'
    assert result['error']['code'] == MCPError.INVALID_TIMEZONE


# ---------------------------------------------------------------------------
# Nightly forecast — error paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_nightly_forecast_invalid_coords():
    """``get_nightly_forecast.fn`` returns structured error for invalid coordinates."""
    result = await get_nightly_forecast.fn(
        lon=200.0,  # invalid
        lat=40.0,
        time='2024-06-15 22:00:00',
        time_zone='America/New_York',
    )

    assert result['_meta']['status'] == 'error'
    assert result['error']['code'] == MCPError.INVALID_COORDINATES


@pytest.mark.asyncio
async def test_get_nightly_forecast_invalid_timezone():
    """``get_nightly_forecast.fn`` returns structured error for invalid timezone."""
    result = await get_nightly_forecast.fn(
        lon=-74.0,
        lat=40.0,
        time='2024-06-15 22:00:00',
        time_zone='Not/A_Zone',
    )

    assert result['_meta']['status'] == 'error'
    assert result['error']['code'] == MCPError.INVALID_TIMEZONE


# ---------------------------------------------------------------------------
# Light pollution map — error paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_light_pollution_map_invalid_bounds():
    """``light_pollution_map.fn`` raises MCPError for invalid bounding box."""
    with patch('src.functions.places.impl.get_light_pollution_grid') as mock_grid:
        mock_grid.side_effect = ValueError('south must be less than north')

        with pytest.raises(MCPError) as exc_info:
            await light_pollution_map.fn(south=40.5, west=-74.0, north=40.0, east=-73.0)

    assert exc_info.value.code == MCPError.EXTERNAL_API_ERROR


@pytest.mark.asyncio
async def test_light_pollution_map_spf_not_installed():
    """``light_pollution_map.fn`` raises CONFIGURATION_ERROR when SPF is missing."""
    with patch(
        'src.functions.places.impl.get_light_pollution_grid',
        side_effect=ModuleNotFoundError('No module named stargazing_place_finder'),
    ):
        with pytest.raises(MCPError) as exc_info:
            await light_pollution_map.fn(south=40.0, west=-74.0, north=40.5, east=-73.5)

    assert exc_info.value.code == MCPError.CONFIGURATION_ERROR
    assert 'not installed' in exc_info.value.message


@pytest.mark.asyncio
async def test_light_pollution_map_spf_data_error():
    """``light_pollution_map.fn`` translates SPF DataError to MCPError."""
    try:
        from stargazingplacefinder import DataError  # noqa: F401

        with patch(
            'src.functions.places.impl.get_light_pollution_grid',
            side_effect=DataError('GeoTIFF not found'),
        ):
            with pytest.raises(MCPError) as exc_info:
                await light_pollution_map.fn(south=40.0, west=-74.0, north=40.5, east=-73.5)
        assert exc_info.value.code in (
            MCPError.EXTERNAL_API_ERROR,
            MCPError.CONFIGURATION_ERROR,
        )
    except ImportError:
        pytest.skip('stargazingplacefinder not available in this environment')
