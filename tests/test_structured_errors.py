from unittest.mock import patch

import pytest

from src.functions.celestial.impl import (
    get_celestial_pos,
    get_celestial_rise_set,
    get_constellation,
    get_moon_info,
    get_nightly_forecast,
    list_visible_planets,
)
from src.functions.weather.impl import (
    _get_qweather_auth_from_env,
    get_weather_by_name,
)
from src.response import MCPError, format_error
from src.utils import create_earth_location, parse_datetime


def test_mcperror_constants():
    """Test that MCPError has all the expected error code constants."""
    assert hasattr(MCPError, 'INVALID_COORDINATES')
    assert hasattr(MCPError, 'INVALID_TIMEZONE')
    assert hasattr(MCPError, 'INVALID_TIME_FORMAT')
    assert hasattr(MCPError, 'MISSING_API_KEY')
    assert hasattr(MCPError, 'API_AUTH_FAILURE')
    assert hasattr(MCPError, 'API_TIMEOUT')
    assert hasattr(MCPError, 'API_RATE_LIMIT')
    assert hasattr(MCPError, 'EXTERNAL_API_ERROR')
    assert hasattr(MCPError, 'NETWORK_ERROR')
    assert hasattr(MCPError, 'CONFIGURATION_ERROR')


def test_mcperror_to_response():
    """Test that MCPError can convert itself to a response dict."""
    error = MCPError('TEST_CODE', 'Test message', {'key': 'value'})
    response = error.to_response()

    assert response['error']['code'] == 'TEST_CODE'
    assert response['error']['message'] == 'Test message'
    assert response['error']['details']['key'] == 'value'
    assert response['_meta']['status'] == 'error'


def test_format_error_function():
    """Test the format_error utility function."""
    response = format_error('TEST_CODE', 'Test message', {'key': 'value'})

    assert response['error']['code'] == 'TEST_CODE'
    assert response['error']['message'] == 'Test message'
    assert response['error']['details']['key'] == 'value'
    assert response['_meta']['status'] == 'error'


def test_invalid_coordinates_error():
    """Test that invalid coordinates raise MCPError."""
    with pytest.raises(MCPError) as exc_info:
        create_earth_location(91, 0)  # Invalid latitude

    error = exc_info.value
    assert error.code == MCPError.INVALID_COORDINATES
    assert 'lat=91' in error.message
    assert error.details['lat'] == 91
    assert error.details['lon'] == 0


def test_invalid_timezone_error():
    """Test that invalid timezone raises MCPError."""
    with pytest.raises(MCPError) as exc_info:
        parse_datetime('2023-01-01', '12:00:00', 'Invalid/Timezone')

    error = exc_info.value
    assert error.code == MCPError.INVALID_TIMEZONE
    assert 'Invalid/Timezone' in error.message


def test_invalid_time_format_error():
    """Test that invalid time format returns a structured MCP error response."""

    async def run_test():
        result = await get_moon_info.fn('invalid-time-format', 'UTC')

        assert result['_meta']['status'] == 'error'
        assert result['error']['code'] == MCPError.INVALID_TIME_FORMAT
        assert 'invalid-time-format' in result['error']['message']

    import asyncio

    asyncio.run(run_test())


@pytest.mark.asyncio
async def test_celestial_position_invalid_coordinates_return_structured_error():
    """Coordinate validation for celestial tools should return the business error shape."""
    result = await get_celestial_pos.fn(
        celestial_object='sun',
        lon=181.0,
        lat=40.0,
        time='2024-06-15 12:00:00',
        time_zone='UTC',
    )

    assert result['_meta']['status'] == 'error'
    assert result['error']['code'] == MCPError.INVALID_COORDINATES
    assert result['error']['details']['lon'] == 181.0


@pytest.mark.asyncio
async def test_celestial_position_invalid_timezone_returns_structured_error():
    """Timezone validation for celestial tools should return the business error shape."""
    with patch('src.functions.celestial.impl.celestial_pos', return_value=(10.0, 120.0)):
        result = await get_celestial_pos.fn(
            celestial_object='sun',
            lon=120.0,
            lat=30.0,
            time='2024-06-15 12:00:00',
            time_zone='Invalid/Timezone',
        )

    assert result['_meta']['status'] == 'error'
    assert result['error']['code'] == MCPError.INVALID_TIMEZONE
    assert result['error']['details']['timezone'] == 'Invalid/Timezone'


@pytest.mark.asyncio
async def test_moon_info_invalid_timezone_returns_structured_error():
    """Moon info should translate invalid timezones into the standard error payload."""
    result = await get_moon_info.fn('2024-06-15 12:00:00', 'Invalid/Timezone')

    assert result['_meta']['status'] == 'error'
    assert result['error']['code'] == MCPError.INVALID_TIMEZONE
    assert result['error']['details']['timezone'] == 'Invalid/Timezone'


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'tool_fn, kwargs',
    [
        (
            get_celestial_rise_set,
            {
                'celestial_object': 'sun',
                'lon': 181.0,
                'lat': 40.0,
                'time': '2024-06-15 12:00:00',
                'time_zone': 'UTC',
            },
        ),
        (
            list_visible_planets,
            {
                'lon': 181.0,
                'lat': 40.0,
                'time': '2024-06-15 12:00:00',
                'time_zone': 'UTC',
            },
        ),
        (
            get_constellation,
            {
                'constellation_name': 'Orion',
                'lon': 181.0,
                'lat': 40.0,
                'time': '2024-06-15 12:00:00',
                'time_zone': 'UTC',
            },
        ),
        (
            get_nightly_forecast,
            {
                'lon': 181.0,
                'lat': 40.0,
                'time': '2024-06-15 12:00:00',
                'time_zone': 'UTC',
            },
        ),
    ],
)
async def test_other_celestial_tools_invalid_coordinates_return_structured_error(tool_fn, kwargs):
    """All celestial tools should normalize coordinate failures into business error payloads."""
    result = await tool_fn.fn(**kwargs)

    assert result['_meta']['status'] == 'error'
    assert result['error']['code'] == MCPError.INVALID_COORDINATES
    assert result['error']['details']['lon'] == 181.0


@patch.dict('os.environ', {}, clear=True)
def test_missing_api_key_error():
    """Test that missing API key raises MCPError."""
    with pytest.raises(MCPError) as exc_info:
        _get_qweather_auth_from_env()

    error = exc_info.value
    assert error.code == MCPError.MISSING_API_KEY
    assert 'QWEATHER_API_KEY' in error.message


@patch('src.functions.weather.impl.get_aggregated_weather_by_name')
def test_weather_api_error_handling(mock_service):
    """Test that weather API errors return structured error responses."""
    mock_service.side_effect = MCPError(
        MCPError.EXTERNAL_API_ERROR,
        'provider failed',
        {'place_name': 'Test City'},
    )

    result = get_weather_by_name.fn('Test City')

    assert 'error' in result
    assert '_meta' in result
    assert result['_meta']['status'] == 'error'
    assert result['error']['code'] == MCPError.EXTERNAL_API_ERROR
    assert result['error']['details']['place_name'] == 'Test City'


@patch('src.retry.time.sleep')  # Mock sleep to speed up test
@patch('src.functions.weather.impl.get_aggregated_weather_by_name')
def test_weather_retry_logic(mock_service, mock_sleep):
    """Test that weather functions retry on network errors and eventually succeed."""
    # First two calls fail with network error, third succeeds
    mock_service.side_effect = [
        ConnectionError('Network timeout'),
        ConnectionError('Network timeout'),
        {
            'location': {'name': 'Test City', 'lat': 0.0, 'lon': 0.0, 'timezone': None},
            'summary': {'current': {'temperature_c': 20.0}, 'daily': [], 'hourly': []},
            'providers': {},
            'source': {
                'query_mode': 'all',
                'successful_providers': ['open-meteo'],
                'failed_providers': [],
            },
        },
    ]

    result = get_weather_by_name.fn('Test City')

    # Should have been called 3 times (initial + 2 retries)
    assert mock_service.call_count == 3
    # Should have slept twice (between retries)
    assert mock_sleep.call_count == 2
    # Should return success on third try
    assert result['data']['summary']['current']['temperature_c'] == 20.0
