from unittest.mock import MagicMock, patch

import pytest

from src.functions.weather.providers import open_meteo, qweather, wttr
from src.functions.weather.providers._adapter import WeatherProviderAdapter
from src.functions.weather.service import _PROVIDER_ADAPTERS, PROVIDER_ORDER
from src.schemas.weather import CurrentWeather, LocationInfo, NormalizedWeatherData


def test_provider_adapter_runs_fetch_normalize_and_wraps_success():
    normalized = NormalizedWeatherData(
        location=LocationInfo(name='Beijing', lat=39.9, lon=116.4),
        current=CurrentWeather(temperature_c=20.0),
    )
    fetch_raw = MagicMock(return_value={'raw': True})
    normalize = MagicMock(return_value=normalized)
    adapter = WeatherProviderAdapter(
        name='example',
        fetch_raw=fetch_raw,
        normalize=normalize,
    )

    result = adapter.load(
        39.9,
        116.4,
        location_name='Beijing',
        timezone='Asia/Shanghai',
    )

    fetch_raw.assert_called_once_with(39.9, 116.4, timezone='Asia/Shanghai')
    normalize.assert_called_once_with(
        {'raw': True},
        39.9,
        116.4,
        location_name='Beijing',
        timezone='Asia/Shanghai',
    )
    assert result.provider == 'example'
    assert result.data is normalized


def test_provider_registry_matches_provider_order():
    assert PROVIDER_ORDER == ['open-meteo', 'qweather', 'wttr']
    assert set(_PROVIDER_ADAPTERS) == set(PROVIDER_ORDER)


@pytest.mark.parametrize(
    'module',
    [open_meteo, qweather, wttr],
    ids=['open-meteo', 'qweather', 'wttr'],
)
def test_provider_module_wrapper_delegates_to_shared_adapter(module):
    adapter = MagicMock()
    adapter.load.return_value = 'normalized'

    with patch.object(module, 'WEATHER_PROVIDER', adapter):
        result = module.get_weather_by_position(
            39.9,
            116.4,
            location_name='Beijing',
            timezone='Asia/Shanghai',
        )

    assert result == 'normalized'
    adapter.load.assert_called_once_with(
        39.9,
        116.4,
        location_name='Beijing',
        timezone='Asia/Shanghai',
    )
