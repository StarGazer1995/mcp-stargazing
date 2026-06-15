"""wttr.in provider adapter."""

import requests

from src.models.weather import (
    CurrentWeather,
    DailyForecastItem,
    HourlyForecastItem,
    LocationInfo,
    NormalizedWeatherData,
    ProviderSuccess,
)
from src.response import MCPError


def get_weather_by_position(
    lat: float,
    lon: float,
    location_name: str | None = None,
    timezone: str | None = None,
) -> ProviderSuccess:
    """查询 wttr.in 并返回标准化后的 provider 结果。"""

    raw_data = fetch_wttr_raw_weather(lat, lon)
    normalized = normalize_wttr_weather(
        raw_data,
        lat,
        lon,
        location_name=location_name,
        timezone=timezone,
    )
    return ProviderSuccess(provider='wttr', data=normalized)


def build_wttr_query(lat: float, lon: float) -> str:
    """构造 wttr.in 查询字符串。"""

    return f'{lat},{lon}'


def fetch_wttr_raw_weather(lat: float, lon: float) -> dict:
    """查询 wttr.in 原始天气数据。"""

    try:
        response = requests.get(
            f'https://wttr.in/{build_wttr_query(lat, lon)}',
            params={'format': 'j1'},
            timeout=15.0,
        )
        response.raise_for_status()
    except requests.exceptions.Timeout as exc:
        raise MCPError(
            MCPError.API_TIMEOUT,
            'wttr.in 请求超时。',
            {'lat': lat, 'lon': lon},
        ) from exc
    except requests.exceptions.ConnectionError as exc:
        raise MCPError(
            MCPError.NETWORK_ERROR,
            'wttr.in 网络连接失败。',
            {'lat': lat, 'lon': lon},
        ) from exc
    except requests.exceptions.HTTPError as exc:
        raise MCPError(
            MCPError.EXTERNAL_API_ERROR,
            f'wttr.in 返回 HTTP {response.status_code}。',
            {'lat': lat, 'lon': lon, 'status_code': response.status_code},
        ) from exc
    except requests.exceptions.RequestException as exc:
        raise MCPError(
            MCPError.NETWORK_ERROR,
            f'wttr.in 请求失败: {exc}',
            {'lat': lat, 'lon': lon},
        ) from exc

    try:
        return response.json()
    except ValueError as exc:
        raise MCPError(
            MCPError.EXTERNAL_API_ERROR,
            'wttr.in 返回了无效 JSON。',
            {'lat': lat, 'lon': lon},
        ) from exc


def normalize_wttr_weather(
    raw_data: dict,
    lat: float,
    lon: float,
    location_name: str | None = None,
    timezone: str | None = None,
) -> NormalizedWeatherData:
    """将 wttr.in 原始响应映射为统一天气结构。"""

    current = (raw_data.get('current_condition') or [{}])[0]
    weather_rows = raw_data.get('weather', [])
    nearest_area = (raw_data.get('nearest_area') or [{}])[0]
    if location_name is None:
        area_names = nearest_area.get('areaName') or []
        if area_names:
            location_name = area_names[0].get('value')

    daily_items: list[DailyForecastItem] = []
    hourly_items: list[HourlyForecastItem] = []
    for weather_row in weather_rows:
        hourly_rows = weather_row.get('hourly') or []
        daily_items.append(
            DailyForecastItem(
                date=weather_row.get('date'),
                temp_min_c=_to_float(weather_row.get('mintempC')),
                temp_max_c=_to_float(weather_row.get('maxtempC')),
                precipitation_probability=_hourly_max_ratio(hourly_rows, 'chanceofrain'),
                cloud_cover_percent=_hourly_average(hourly_rows, 'cloudcover'),
                weather_code_day=map_wttr_condition_text(
                    _condition_text_from_row(hourly_rows[0]) if hourly_rows else None
                ),
                weather_text_day=_condition_text_from_row(hourly_rows[0]) if hourly_rows else None,
            )
        )
        hourly_items.extend(_build_hourly_items(weather_row.get('date'), hourly_rows))

    return NormalizedWeatherData(
        location=LocationInfo(
            name=location_name,
            lat=lat,
            lon=lon,
            timezone=timezone,
        ),
        current=CurrentWeather(
            temperature_c=_to_float(current.get('temp_C')),
            feels_like_c=_to_float(current.get('FeelsLikeC')),
            humidity=_to_float(current.get('humidity')),
            wind_speed_kph=_to_float(current.get('windspeedKmph')),
            wind_direction_deg=_to_float(current.get('winddirDegree')),
            pressure_hpa=_to_float(current.get('pressure')),
            visibility_km=_to_float(current.get('visibility')),
            cloud_cover_percent=_to_float(current.get('cloudcover')),
            cloud_cover_low_percent=None,
            cloud_cover_mid_percent=None,
            cloud_cover_high_percent=None,
            weather_code=map_wttr_condition_text(_condition_text_from_row(current)),
            weather_text=_condition_text_from_row(current),
            observation_time=current.get('localObsDateTime'),
        ),
        daily=[item for item in daily_items if item.date],
        hourly=hourly_items,
    )


def map_wttr_condition_text(text: str | None) -> str | None:
    """将 wttr.in 的天气文本映射为内部统一 weather_code。"""

    if text is None:
        return None
    normalized = text.lower()
    if 'sun' in normalized or 'clear' in normalized:
        return 'clear'
    if 'cloud' in normalized or 'overcast' in normalized:
        return 'partly_cloudy'
    if 'rain' in normalized or 'drizzle' in normalized or 'shower' in normalized:
        return 'rain'
    if 'snow' in normalized or 'ice' in normalized or 'blizzard' in normalized:
        return 'snow'
    if 'fog' in normalized or 'mist' in normalized or 'haze' in normalized:
        return 'fog'
    if 'thunder' in normalized:
        return 'thunderstorm'
    return 'unknown'


def _build_hourly_items(
    date_value: str | None, hourly_rows: list[dict]
) -> list[HourlyForecastItem]:
    """构造 wttr.in 的小时级预报列表。"""

    items: list[HourlyForecastItem] = []
    for row in hourly_rows:
        time_value = _combine_wttr_date_and_time(date_value, row.get('time'))
        if time_value is None:
            continue
        items.append(
            HourlyForecastItem(
                time=time_value,
                temperature_c=_to_float(row.get('tempC')),
                humidity=_to_float(row.get('humidity')),
                precipitation_probability=_percent_text_to_ratio(row.get('chanceofrain')),
                wind_speed_kph=_to_float(row.get('windspeedKmph')),
                wind_direction_deg=_to_float(row.get('winddirDegree')),
                cloud_cover_percent=_to_float(row.get('cloudcover')),
                cloud_cover_low_percent=None,
                cloud_cover_mid_percent=None,
                cloud_cover_high_percent=None,
                weather_code=map_wttr_condition_text(_condition_text_from_row(row)),
                weather_text=_condition_text_from_row(row),
            )
        )
    return items


def _combine_wttr_date_and_time(date_value: str | None, time_value: str | None) -> str | None:
    """将 wttr.in 的日期和时间字段拼成 ISO 风格的时间字符串。"""

    if not date_value or time_value is None:
        return None
    hour = int(time_value) // 100
    if hour == 24:
        hour = 0
    return f'{date_value}T{hour:02d}:00:00'


def _condition_text_from_row(row: dict) -> str | None:
    """从 wttr.in 行数据中提取天气文本。"""

    values = row.get('weatherDesc') or []
    if values and isinstance(values, list):
        return values[0].get('value')
    return None


def _to_float(value: str | int | float | None) -> float | None:
    """将输入值安全转换为浮点数。"""

    if value in (None, ''):
        return None
    return float(value)


def _percent_text_to_ratio(value: str | int | float | None) -> float | None:
    """将百分比文本转换为 0 到 1 之间的小数。"""

    numeric = _to_float(value)
    if numeric is None:
        return None
    return numeric / 100.0


def _hourly_average(rows: list[dict], key: str) -> float | None:
    """计算逐小时字段的平均值。"""

    values = [_to_float(row.get(key)) for row in rows if _to_float(row.get(key)) is not None]
    if not values:
        return None
    return sum(values) / len(values)


def _hourly_max_ratio(rows: list[dict], key: str) -> float | None:
    """计算逐小时百分比字段的最大值并转为小数。"""

    values = [_to_float(row.get(key)) for row in rows if _to_float(row.get(key)) is not None]
    if not values:
        return None
    return max(values) / 100.0
