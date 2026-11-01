"""Atmospheric evidence is part of weather aggregation, with independent data quality."""

import copy
import json
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from fastmcp import Client

from src.functions.weather import impl, service
from src.functions.weather.providers import atmosphere as a
from src.functions.weather.providers import open_meteo
from src.response import MCPError
from src.schemas.weather import CurrentWeather, LocationInfo, NormalizedWeatherData, ProviderSuccess
from src.server_instance import mcp

NOW = datetime(2026, 11, 1, 8, 30, tzinfo=UTC)


@pytest.fixture
def raw(monkeypatch):
    monkeypatch.setattr(open_meteo, 'utc_now', lambda: NOW)
    weather = {
        'latitude': 31.2,
        'longitude': 121.5,
        'elevation': 3,
        'timezone': 'Asia/Shanghai',
        'current': {'time': '2026-11-01T16:30', 'temperature_2m': 22},
        'hourly': {
            'time': ['2026-11-01T15:00', '2026-11-01T16:00', '2026-11-01T17:00'],
            'boundary_layer_height': [800, 600, 500],
            'visibility': [10000, 8000, 6000],
        },
        'hourly_units': {'boundary_layer_height': 'm', 'visibility': 'm'},
    }
    weather['_air_quality'] = {
        'latitude': 31.1,
        'longitude': 121.4,
        'timezone': 'UTC',
        'hourly': {
            'time': [int(datetime(2026, 11, 1, h, tzinfo=UTC).timestamp()) for h in (7, 8, 9)],
            **{variable: [0, 38, 40] for variable, _ in a.AIR_FIELDS.values()},
        },
        'hourly_units': {'time': 'unixtime', **{v: u for v, u in a.AIR_FIELDS.values()}},
    }
    return weather


def normalized(raw):
    return open_meteo.normalize_open_meteo_weather(raw, 31.11, 121.38)


def test_state_is_nested_in_weather_with_its_own_time_and_sources(raw):
    data = normalized(raw)
    assert data.current.temperature_c == 22
    assert data.current.observation_time == '2026-11-01T16:30'
    state = data.current.atmosphere
    assert state.time == '2026-11-01T08:00:00+00:00'
    assert state.pm2_5_ug_m3 == 38
    assert state.visibility_km == 8
    assert state.boundary_layer_height_m == 600
    assert state.field_sources['pm2_5_ug_m3'] == a.AIR_SOURCE
    assert state.field_sources['visibility_km'] == a.WEATHER_SOURCE
    assert [item.atmosphere.temporal_role for item in data.hourly] == [
        'past_model_estimate',
        'current_model_estimate',
        'forecast',
    ]
    assert data.hourly[0].atmosphere.pm2_5_ug_m3 == 0
    for source in data.atmosphere_sources.values():
        assert source.data_kind == 'model_estimate'
        assert source.model_run_time is None
        assert source.retrieved_at == NOW.isoformat()
    assert data.atmosphere_sources[a.AIR_SOURCE].units['pm2_5_ug_m3'] == 'μg/m³'
    json.dumps(data.model_dump(), allow_nan=False)


def test_aggregation_exposes_the_same_nested_fields(raw, monkeypatch):
    result = ProviderSuccess(provider='open-meteo', data=normalized(raw))
    adapter = MagicMock()
    adapter.load.return_value = result
    monkeypatch.setitem(service._PROVIDER_ADAPTERS, 'open-meteo', adapter)
    payload = impl.get_weather_by_position.fn(31.11, 121.38, provider='open-meteo')['data']
    assert payload['summary']['current']['atmosphere']['pm2_5_ug_m3'] == 38
    assert payload['summary']['hourly'][2]['atmosphere']['pm2_5_ug_m3'] == 40
    assert payload['summary']['atmosphere_sources'][a.AIR_SOURCE]['status'] == 'success'
    assert payload['providers']['open-meteo']['data']['current'] == payload['summary']['current']


def test_name_entry_uses_the_same_aggregation(raw, monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(
        service,
        'resolve_place_name',
        lambda name: SimpleNamespace(lat=31.11, lon=121.38, name=name, timezone='Asia/Shanghai'),
    )
    adapter = MagicMock()
    adapter.load.return_value = ProviderSuccess(provider='open-meteo', data=normalized(raw))
    monkeypatch.setitem(service._PROVIDER_ADAPTERS, 'open-meteo', adapter)
    result = impl.get_weather_by_name.fn('上海闵行', provider='open-meteo')['data']
    assert result['summary']['current']['atmosphere']['pm2_5_ug_m3'] == 38


def test_provider_filter_does_not_trigger_hidden_air_requests(monkeypatch):
    adapter = MagicMock()
    adapter.load.return_value = ProviderSuccess(
        provider='qweather',
        data=NormalizedWeatherData(
            location=LocationInfo(lat=31, lon=121), current=CurrentWeather(temperature_c=20)
        ),
    )
    monkeypatch.setitem(service._PROVIDER_ADAPTERS, 'qweather', adapter)
    forbidden = MagicMock(side_effect=AssertionError('unexpected air request'))
    monkeypatch.setattr(open_meteo, 'fetch_air_quality', forbidden)
    result = service.get_aggregated_weather_by_position(31, 121, provider='qweather')
    assert result.summary.current['atmosphere'] is None
    assert result.summary.atmosphere_sources == {}
    forbidden.assert_not_called()


def test_air_gaps_and_horizon_are_not_filled_by_position_or_nearest_hour(raw):
    raw['_air_quality']['hourly']['time'][1] += 86400
    data = normalized(raw)
    assert data.hourly[1].atmosphere.pm2_5_ug_m3 is None
    assert data.hourly[1].atmosphere.boundary_layer_height_m == 600
    assert data.hourly[2].atmosphere.pm2_5_ug_m3 == 40
    # No air row at the requested weather hour is not clear air.
    raw['hourly']['time'][2] = '2026-11-09T17:00'
    assert normalized(raw).hourly[2].atmosphere.pm2_5_ug_m3 is None


def test_missing_units_invalid_values_and_truncated_arrays_remain_unknown(raw):
    air = raw['_air_quality']
    air['hourly_units']['pm2_5'] = 'μg/mL'
    air['hourly']['pm10'] = [100]
    air['hourly']['ozone'] = [float('nan'), -2, True]
    air['hourly_units']['nitrogen_dioxide'] = 'µg/m³'
    raw['hourly']['boundary_layer_height'] = [float('inf'), 600, 500]
    data = normalized(raw)
    for item in data.hourly:
        assert item.atmosphere.pm2_5_ug_m3 is None
        assert item.atmosphere.pm10_ug_m3 is None
        assert item.atmosphere.o3_ug_m3 is None
    assert data.current.atmosphere.no2_ug_m3 == 38
    assert data.atmosphere_sources[a.AIR_SOURCE].status == 'partial'
    assert data.hourly[0].atmosphere.boundary_layer_height_m is None
    json.dumps(data.model_dump(), allow_nan=False)


@pytest.mark.parametrize('bad', [[], {}, None, {'hourly': {}, 'hourly_units': {}}])
def test_bad_air_payload_keeps_weather(raw, bad):
    raw['_air_quality'] = bad
    data = normalized(raw)
    assert data.current.temperature_c == 22
    assert data.current.atmosphere.pm2_5_ug_m3 is None
    assert data.atmosphere_sources[a.AIR_SOURCE].status == 'error'


@pytest.mark.parametrize('times', [[1, 1, 2], [None, 1, 2], 'bad'])
def test_bad_air_time_column_never_becomes_a_valid_join(raw, times):
    raw['_air_quality']['hourly']['time'] = times
    data = normalized(raw)
    assert data.current.atmosphere.pm2_5_ug_m3 is None


def test_wrong_unix_unit_fails_the_air_source(raw):
    raw['_air_quality']['hourly_units']['time'] = 'iso8601'
    assert normalized(raw).atmosphere_sources[a.AIR_SOURCE].status == 'error'


def test_missing_all_atmospheric_data_is_null_without_losing_weather(raw):
    raw.pop('_air_quality')
    raw.pop('hourly_units')
    data = normalized(raw)
    assert data.current.atmosphere is None
    assert all(item.atmosphere is None for item in data.hourly)
    assert data.current.temperature_c == 22


def test_all_null_air_columns_are_an_unavailable_source(raw):
    air = raw['_air_quality']
    for variable, _ in a.AIR_FIELDS.values():
        air['hourly'][variable] = [None, None, None]
    data = normalized(raw)
    assert data.atmosphere_sources[a.AIR_SOURCE].status == 'error'
    assert data.current.atmosphere.boundary_layer_height_m == 600


def test_invalid_weather_hour_is_unknown_and_midnight_join_uses_timezone(raw):
    raw['hourly']['time'][0] = 'bad'
    raw['hourly']['time'][2] = '2026-11-02T00:00'
    raw['_air_quality']['hourly']['time'][2] = int(
        datetime(2026, 11, 1, 16, tzinfo=UTC).timestamp()
    )
    data = normalized(raw)
    assert data.hourly[0].atmosphere is None
    assert data.hourly[2].atmosphere.time == '2026-11-01T16:00:00+00:00'
    assert data.hourly[2].atmosphere.pm2_5_ug_m3 == 40


def test_fetch_reuses_weather_and_air_failure_is_an_independent_error(raw, monkeypatch):
    calls = []

    def weather(*args, **kwargs):
        calls.append(kwargs['params'])
        return copy.deepcopy(raw)

    monkeypatch.setattr(open_meteo, 'fetch_weather_json', weather)
    monkeypatch.setattr(
        open_meteo,
        'fetch_air_quality',
        MagicMock(side_effect=MCPError(MCPError.API_TIMEOUT, 'air timeout')),
    )
    fetched = open_meteo.fetch_open_meteo_raw_weather(31.11, 121.38)
    data = normalized(fetched)
    assert len(calls) == 1
    assert 'boundary_layer_height' in calls[0]['hourly']
    assert 'visibility' in calls[0]['hourly']
    assert data.atmosphere_sources[a.AIR_SOURCE].error_code == MCPError.API_TIMEOUT
    assert data.current.temperature_c == 22


def test_fetch_attaches_successful_air_payload(raw, monkeypatch):
    monkeypatch.setattr(open_meteo, 'fetch_weather_json', lambda *args, **kwargs: raw)
    monkeypatch.setattr(open_meteo, 'fetch_air_quality', lambda *args: raw['_air_quality'])
    assert open_meteo.fetch_open_meteo_raw_weather(31, 121)['_air_quality'] == raw['_air_quality']


@pytest.mark.parametrize(
    'code',
    [
        MCPError.API_TIMEOUT,
        MCPError.NETWORK_ERROR,
        MCPError.API_RATE_LIMIT,
        MCPError.EXTERNAL_API_ERROR,
    ],
)
def test_air_transport_retry_policy(monkeypatch, raw, code):
    calls = []

    def fetch(*args, **kwargs):
        calls.append(kwargs)
        raise MCPError(code, 'unavailable')

    monkeypatch.setattr(a, 'fetch_weather_json', fetch)
    monkeypatch.setattr(a.time, 'sleep', lambda seconds: None)
    with pytest.raises(MCPError):
        a.fetch_air_quality(31, 121)
    assert len(calls) == (1 if code == MCPError.EXTERNAL_API_ERROR else 3)


def test_air_request_is_explicitly_global_and_bounded(monkeypatch, raw):
    fetch = MagicMock(return_value=raw['_air_quality'])
    monkeypatch.setattr(a, 'fetch_weather_json', fetch)
    a.fetch_air_quality(31, 121)
    params = fetch.call_args.kwargs['params']
    assert params['domains'] == 'cams_global'
    assert params['forecast_days'] == 5
    assert params['timeformat'] == 'unixtime'


@pytest.mark.parametrize(
    'value,zone',
    [
        ('bad', 'UTC'),
        ('2026-11-01T01:00', 'America/New_York'),
        ('2026-03-08T02:00', 'America/New_York'),
        ('2026-11-01T08:00', 'Bad/Zone'),
        (10**100, 'UTC'),
    ],
)
def test_invalid_or_dst_ambiguous_time_is_unknown(value, zone):
    assert a._timestamp(value, zone) is None


def test_current_time_missing_does_not_reuse_first_forecast_hour(raw):
    raw['current']['time'] = 'bad'
    assert normalized(raw).current.atmosphere is None


def test_signed_grid_metadata_and_no_finite_overflow(raw):
    raw['_air_quality']['latitude'] = -31
    raw['_air_quality']['longitude'] = -121
    raw['_air_quality']['elevation'] = -10
    raw['_air_quality']['hourly']['pm2_5'] = [10**1000, None, -1]
    result = normalized(raw)
    assert result.atmosphere_sources[a.AIR_SOURCE].grid_lat == -31
    assert result.current.atmosphere.pm2_5_ug_m3 is None


def test_real_clock_is_aware():
    assert a.utc_now().tzinfo is UTC


@pytest.mark.asyncio
async def test_sdk_uses_existing_weather_tools(raw, monkeypatch):
    monkeypatch.setattr(
        impl,
        'fetch_weather_by_position_capability',
        lambda *args: service._build_summary(
            [ProviderSuccess(provider='open-meteo', data=normalized(raw))]
        ).model_dump(),
    )
    async with Client(mcp._mcp) as client:
        tools = {tool.name for tool in await client.list_tools()}
        assert 'get_atmospheric_conditions' not in tools
        result = await client.call_tool('get_weather_by_position', {'lat': 31.11, 'lon': 121.38})
    assert result.structured_content['data']['current']['atmosphere']['pm2_5_ug_m3'] == 38
