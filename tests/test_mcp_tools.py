"""Tests for MCP tool wrappers not covered by other test files."""

from unittest.mock import MagicMock, patch

import pytest

from src.functions.celestial.impl import (
    get_constellation,
    get_moon_info,
    get_nightly_forecast,
    list_visible_planets,
)
from src.functions.metadata.impl import get_tool_catalog
from src.functions.places.impl import light_pollution_map
from src.functions.time.impl import get_local_datetime_info
from src.functions.weather.impl import get_weather_by_name, get_weather_by_position
from src.response import MCPError

EXPECTED_TOOLS = {
    'analysis_area',
    'get_celestial_pos',
    'get_celestial_rise_set',
    'get_constellation',
    'get_local_datetime_info',
    'get_moon_info',
    'get_nightly_forecast',
    'get_tool_catalog',
    'get_weather_by_name',
    'get_weather_by_position',
    'light_pollution_map',
    'list_visible_planets',
}

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
