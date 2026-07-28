import os
from unittest.mock import Mock, patch

import pytest

from src.functions.weather.impl import get_weather_by_name, get_weather_by_position
from src.functions.weather.providers.open_meteo import fetch_open_meteo_raw_weather
from src.functions.weather.providers.wttr import fetch_wttr_raw_weather
from src.qweather_interaction import (
    qweather_get_poi,
    qweather_get_weather_by_coord_in_ten_days,
    qweather_get_weather_by_coord_in_twenty_four_hours,
    qweather_get_weather_by_coord_real_time,
)
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


def test_qweather_interaction_builds_url_then_delegates_to_shared_http_helper():
    with patch(
        'src.qweather_interaction.fetch_qweather_json',
        return_value={'code': '200'},
    ) as mock_fetch:
        result = qweather_get_weather_by_coord_real_time(
            116.4,
            39.9,
            'demo-key',
            api_host='api.example.com',
            jwt_token='demo-jwt',
        )

    assert result == {'code': '200'}
    mock_fetch.assert_called_once_with(
        'https://api.example.com/v7/weather/now?location=116.4,39.9',
        'demo-key',
        jwt_token='demo-jwt',
    )


def test_qweather_poi_uses_default_geo_host_from_helper():
    with (
        patch('src.qweather_interaction.get_qweather_api_host', return_value='geo.example.com'),
        patch(
            'src.qweather_interaction.fetch_qweather_json',
            return_value={'code': '200'},
        ) as mock_fetch,
    ):
        result = qweather_get_poi('beijing', 'demo-key', jwt_token='demo-jwt')

    assert result == {'code': '200'}
    mock_fetch.assert_called_once_with(
        'https://geo.example.com/geo/v2/poi/lookup?type=scenic&location=beijing',
        'demo-key',
        jwt_token='demo-jwt',
    )


def test_qweather_forecast_helpers_delegate_to_shared_http_helper():
    with patch(
        'src.qweather_interaction.fetch_qweather_json',
        return_value={'code': '200'},
    ) as mock_fetch:
        ten_days = qweather_get_weather_by_coord_in_ten_days(
            116.4,
            39.9,
            'demo-key',
            api_host='api.example.com',
            jwt_token='demo-jwt',
        )
        hourly = qweather_get_weather_by_coord_in_twenty_four_hours(
            116.4,
            39.9,
            'demo-key',
            api_host='api.example.com',
            jwt_token='demo-jwt',
        )

    assert ten_days == {'code': '200'}
    assert hourly == {'code': '200'}
    assert mock_fetch.call_args_list == [
        (
            ('https://api.example.com/v7/weather/10d?location=116.4,39.9', 'demo-key'),
            {'jwt_token': 'demo-jwt'},
        ),
        (
            ('https://api.example.com/v7/weather/24h?location=116.4,39.9', 'demo-key'),
            {'jwt_token': 'demo-jwt'},
        ),
    ]


def test_wttr_fetch_uses_shared_http_helper():
    with patch(
        'src.functions.weather.providers.wttr.fetch_weather_json',
        return_value={'current_condition': []},
    ) as mock_fetch:
        result = fetch_wttr_raw_weather(40.0, 116.0)

    assert result == {'current_condition': []}
    mock_fetch.assert_called_once_with(
        'https://wttr.in/40.0,116.0',
        service_name='wttr.in',
        context={'lat': 40.0, 'lon': 116.0},
        params={'format': 'j1'},
    )


def test_open_meteo_fetch_uses_shared_json_error_translation():
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.side_effect = ValueError('invalid json')

    with patch('src.functions.weather.providers._http.requests.get', return_value=response):
        with pytest.raises(MCPError) as exc_info:
            fetch_open_meteo_raw_weather(40.0, 116.0)

    error = exc_info.value
    assert error.code == MCPError.EXTERNAL_API_ERROR
    assert 'Open-Meteo' in error.message
    assert error.details == {'lat': 40.0, 'lon': 116.0}
