import os
from unittest.mock import patch

import pytest

from src.functions.weather.impl import get_weather_by_name, get_weather_by_position
from src.response import MCPError
from src.schemas import AggregatedWeatherResponse


def test_get_weather_by_name_no_api_key():
    with patch.dict(os.environ, clear=True):
        if 'QWEATHER_API_KEY' in os.environ:
            del os.environ['QWEATHER_API_KEY']

        with pytest.raises(MCPError, match='QWEATHER_API_KEY|QWEATHER_JWT_TOKEN'):
            # Use .fn to call the underlying function
            from src.functions.weather.impl import _get_qweather_auth_from_env

            _get_qweather_auth_from_env()


def test_get_weather_by_name_success():
    aggregated_result = {
        'location': {'name': 'Beijing', 'lat': 39.9, 'lon': 116.4, 'timezone': 'Asia/Shanghai'},
        'summary': {
            'current': {'temperature_c': 20.0, 'cloud_cover_percent': 50.0},
            'daily': [],
            'hourly': [{'time': '2026-06-15T10:00:00+08:00', 'cloud_cover_percent': 55.0}],
        },
        'providers': {},
        'source': {
            'query_mode': 'all',
            'successful_providers': ['open-meteo'],
            'failed_providers': [],
        },
    }
    with patch('src.functions.weather.impl.get_aggregated_weather_by_name') as mock_service:
        mock_service.return_value = aggregated_result
        result = get_weather_by_name.fn('Beijing')

        assert 'data' in result
        assert result['data'] == aggregated_result
        assert result['_meta']['status'] == 'success'
        mock_service.assert_called_with('Beijing', provider='all')


def test_get_weather_by_position_success():
    aggregated_result = {
        'location': {'name': None, 'lat': 40.0, 'lon': 116.0, 'timezone': 'Asia/Shanghai'},
        'summary': {
            'current': {'temperature_c': 20.0, 'cloud_cover_percent': 40.0},
            'daily': [],
            'hourly': [{'time': '2026-06-15T10:00:00+08:00', 'cloud_cover_percent': 42.0}],
        },
        'providers': {},
        'source': {
            'query_mode': 'all',
            'successful_providers': ['open-meteo'],
            'failed_providers': [],
        },
    }
    with patch('src.functions.weather.impl.get_aggregated_weather_by_position') as mock_service:
        mock_service.return_value = aggregated_result
        result = get_weather_by_position.fn(40.0, 116.0)

        assert 'data' in result
        assert result['data'] == aggregated_result
        mock_service.assert_called_with(40.0, 116.0, provider='all')


def test_get_weather_by_name_mcperror_returns_structured_error():
    with patch('src.functions.weather.impl.get_aggregated_weather_by_name') as mock_service:
        mock_service.side_effect = MCPError(
            MCPError.API_TIMEOUT,
            'provider timeout',
            {'place_name': 'Beijing'},
        )

        result = get_weather_by_name.fn('Beijing')

    assert result['_meta']['status'] == 'error'
    assert result['error']['code'] == MCPError.API_TIMEOUT
    assert result['error']['details']['place_name'] == 'Beijing'


def test_get_weather_by_position_mcperror_returns_structured_error():
    with patch('src.functions.weather.impl.get_aggregated_weather_by_position') as mock_service:
        mock_service.side_effect = MCPError(
            MCPError.API_RATE_LIMIT,
            'provider rate limited',
            {'lat': 40.0, 'lon': 116.0},
        )

        result = get_weather_by_position.fn(40.0, 116.0)

    assert result['_meta']['status'] == 'error'
    assert result['error']['code'] == MCPError.API_RATE_LIMIT
    assert result['error']['details'] == {'lat': 40.0, 'lon': 116.0}


def test_get_weather_by_name_aggregated_model_is_dumped():
    aggregated_result = AggregatedWeatherResponse(
        location={'name': 'Beijing', 'lat': 39.9, 'lon': 116.4, 'timezone': 'Asia/Shanghai'},
        summary={'current': {'temperature_c': 20.0}, 'daily': [], 'hourly': []},
        providers={},
        source={
            'query_mode': 'all',
            'successful_providers': ['open-meteo'],
            'failed_providers': [],
        },
    )

    with patch('src.functions.weather.impl.get_aggregated_weather_by_name') as mock_service:
        mock_service.return_value = aggregated_result
        result = get_weather_by_name.fn('Beijing')

    assert result['_meta']['status'] == 'success'
    assert result['data'] == aggregated_result.model_dump()


def test_get_weather_by_position_aggregated_model_is_dumped():
    aggregated_result = AggregatedWeatherResponse(
        location={'name': None, 'lat': 40.0, 'lon': 116.0, 'timezone': 'Asia/Shanghai'},
        summary={'current': {'temperature_c': 18.0}, 'daily': [], 'hourly': []},
        providers={},
        source={
            'query_mode': 'all',
            'successful_providers': ['open-meteo'],
            'failed_providers': [],
        },
    )

    with patch('src.functions.weather.impl.get_aggregated_weather_by_position') as mock_service:
        mock_service.return_value = aggregated_result
        result = get_weather_by_position.fn(40.0, 116.0)

    assert result['_meta']['status'] == 'success'
    assert result['data'] == aggregated_result.model_dump()
