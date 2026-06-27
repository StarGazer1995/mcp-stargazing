from unittest.mock import patch

import pytest

from src.functions.celestial.impl import get_moon_info
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
    """Test that invalid time format raises MCPError."""

    async def run_test():
        with pytest.raises(MCPError) as exc_info:
            await get_moon_info.fn('invalid-time-format', 'UTC')

        error = exc_info.value
        assert error.code == MCPError.INVALID_TIME_FORMAT
        assert 'invalid-time-format' in error.message

    import asyncio

    asyncio.run(run_test())


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
