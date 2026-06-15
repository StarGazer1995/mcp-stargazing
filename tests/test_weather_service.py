from unittest.mock import patch

from src.functions.weather.service import get_aggregated_weather_by_position
from src.models.weather import (
    CurrentWeather,
    DailyForecastItem,
    HourlyForecastItem,
    LocationInfo,
    NormalizedWeatherData,
    ProviderError,
    ProviderSuccess,
)


def test_aggregated_weather_by_position_uses_open_meteo_hourly_first():
    open_meteo_result = ProviderSuccess(
        provider="open-meteo",
        data=NormalizedWeatherData(
            location=LocationInfo(name="Beijing", lat=39.9, lon=116.4, timezone="Asia/Shanghai"),
            current=CurrentWeather(temperature_c=25.0, cloud_cover_percent=60.0),
            daily=[DailyForecastItem(date="2026-06-15", cloud_cover_percent=65.0)],
            hourly=[HourlyForecastItem(time="2026-06-15T10:00:00+08:00", cloud_cover_percent=55.0)],
        ),
    )
    wttr_result = ProviderSuccess(
        provider="wttr",
        data=NormalizedWeatherData(
            location=LocationInfo(name="Beijing", lat=39.9, lon=116.4, timezone=None),
            current=CurrentWeather(temperature_c=24.0, cloud_cover_percent=45.0),
            daily=[DailyForecastItem(date="2026-06-15", cloud_cover_percent=50.0)],
            hourly=[HourlyForecastItem(time="2026-06-15T10:00:00+08:00", cloud_cover_percent=40.0)],
        ),
    )

    with patch("src.functions.weather.service.open_meteo.get_weather_by_position", return_value=open_meteo_result), \
         patch("src.functions.weather.service.qweather.get_weather_by_position", side_effect=Exception("should not be called")), \
         patch("src.functions.weather.service.wttr.get_weather_by_position", return_value=wttr_result):
        result = get_aggregated_weather_by_position(39.9, 116.4, provider="all", location_name="Beijing")

    assert result.summary.current["temperature_c"] == 25.0
    assert result.summary.hourly[0]["cloud_cover_percent"] == 55.0
    assert result.source.successful_providers == ["open-meteo", "wttr"]


def test_aggregated_weather_by_position_keeps_partial_provider_failures():
    open_meteo_result = ProviderSuccess(
        provider="open-meteo",
        data=NormalizedWeatherData(
            location=LocationInfo(name=None, lat=40.0, lon=116.0, timezone="Asia/Shanghai"),
            current=CurrentWeather(temperature_c=22.0, cloud_cover_percent=35.0),
            daily=[],
            hourly=[],
        ),
    )

    with patch("src.functions.weather.service.open_meteo.get_weather_by_position", return_value=open_meteo_result), \
         patch("src.functions.weather.service.qweather.get_weather_by_position", side_effect=Exception("qweather down")), \
         patch("src.functions.weather.service.wttr.get_weather_by_position", side_effect=Exception("wttr down")):
        result = get_aggregated_weather_by_position(40.0, 116.0, provider="all")

    assert result.summary.current["cloud_cover_percent"] == 35.0
    assert set(result.source.failed_providers) == {"qweather", "wttr"}
