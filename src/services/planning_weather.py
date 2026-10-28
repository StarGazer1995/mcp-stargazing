"""Select dated hourly forecasts without substituting current conditions."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from math import isfinite
from typing import Any

from src.response import MCPError
from src.schemas.celestial import NightWindow
from src.schemas.planning import WeatherPlanningSummary
from src.utils import ensure_timezone, parse_observation_time, parse_time_string


def finite_number(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value):
        return float(value)
    return None


def effective_cloud_cover(item: dict[str, Any]) -> float | None:
    """Do not label an opaque individual cloud layer as a clear sky."""
    values = [
        finite_number(item.get(key))
        for key in (
            'cloud_cover_percent',
            'cloud_cover_low_percent',
            'cloud_cover_mid_percent',
            'cloud_cover_high_percent',
        )
    ]
    known = [value for value in values if value is not None]
    return max(0.0, min(100.0, max(known))) if known else None


@dataclass
class NightWeather:
    hourly: list[dict[str, Any]] = field(default_factory=list)
    summary: WeatherPlanningSummary | None = None
    facts: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def select_night_weather(
    data: dict[str, Any] | None,
    requested_time: str,
    time_zone: str,
    night_window: NightWindow | None = None,
    *,
    full_night: bool = False,
) -> NightWeather:
    """Use one provider's actual forecast hours for this observing interval.

    Providers remain Open-Meteo first, but a short primary horizon must not
    hide another provider's dated forecast. Current/daily values are never a
    substitute for missing hours. Fields absent in hourly data stay unknown.
    """
    result = NightWeather()
    if data is None:
        return result
    start = parse_observation_time(requested_time, time_zone)
    end = start + timedelta(hours=12)
    if night_window is not None:
        dusk = ensure_timezone(parse_time_string(night_window.civil_dusk), time_zone)
        end = ensure_timezone(parse_time_string(night_window.civil_dawn), time_zone)
        start = dusk if full_night else max(start, dusk)

    providers = data.get('providers', {})
    sources = []
    for name in ('open-meteo', 'qweather', 'wttr'):
        provider_data = providers.get(name, {}).get('data', {})
        sources.append(
            (
                name,
                provider_data.get('hourly', []),
                provider_data.get('location', {}).get('timezone') or time_zone,
            )
        )
    sources.append(
        (
            'summary.hourly',
            data.get('summary', {}).get('hourly', []),
            data.get('location', {}).get('timezone') or time_zone,
        )
    )
    selected: list[tuple[datetime, dict[str, Any]]] = []
    source = None
    for name, hourly, source_zone in sources:
        records: dict[datetime, dict[str, Any]] = {}
        for item in hourly:
            try:
                when = ensure_timezone(parse_time_string(item.get('time')), source_zone)
                when = when.astimezone(start.tzinfo)
            except (MCPError, TypeError, ValueError, AttributeError):
                continue
            cloud = effective_cloud_cover(item)
            if not start <= when < end or cloud is None:
                continue
            normalized = {**item, 'time': when.isoformat(), 'cloud_cover_percent': cloud}
            if cloud > (finite_number(item.get('cloud_cover_percent')) or 0.0):
                normalized['weather_text'] = 'Cloudy'
            records[when] = normalized
        if len(records) > len(selected):
            selected = sorted(records.items())
            source = name
    if not selected:
        result.notes.append(
            'nightly_weather_unavailable: 所选夜晚没有可用逐小时云量，未使用当前或日均天气代替。'
        )
        return result

    result.hourly = [item for _, item in selected]

    def mean(key: str) -> float | None:
        values = [finite_number(item.get(key)) for item in result.hourly]
        known = [value for value in values if value is not None]
        return sum(known) / len(known) if known else None

    cloud = mean('cloud_cover_percent')
    precipitation = mean('precipitation_probability')
    result.summary = WeatherPlanningSummary(
        weather_text=(
            'Rain risk'
            if precipitation is not None and precipitation > 0.35
            else 'Clear'
            if cloud <= 25.0
            else 'Cloudy'
        ),
        cloud_cover_percent=cloud,
        visibility_km=mean('visibility_km'),
        wind_speed_kph=mean('wind_speed_kph'),
    )
    result.facts = {
        'time_basis': 'night_hourly_forecast',
        'provider': source,
        'interval_start': start.isoformat(),
        'interval_end': end.isoformat(),
        'first_forecast_time': selected[0][0].isoformat(),
        'last_forecast_time': selected[-1][0].isoformat(),
        'forecast_hours': len(selected),
        'cloud_aggregation': 'mean_of_hourly_max_total_and_layers',
        'precipitation_probability': precipitation,
        **{
            key: mean(key)
            for key in (
                'cloud_cover_low_percent',
                'cloud_cover_mid_percent',
                'cloud_cover_high_percent',
            )
        },
    }
    if (
        selected[0][0] - start > timedelta(hours=1)
        or end - selected[-1][0] > timedelta(hours=1)
        or any(b[0] - a[0] > timedelta(minutes=90) for a, b in zip(selected, selected[1:]))
    ):
        result.notes.append(
            'nightly_weather_partial: 逐小时预报未连续覆盖完整观测时段，天气排序仅供参考。'
        )
    return result
