"""Open-Meteo provider adapter."""

from src.functions.weather.common import http_get_json, to_float
from src.response import MCPError
from src.schemas.weather import (
    CurrentWeather,
    DailyForecastItem,
    HourlyForecastItem,
    LocationInfo,
    NormalizedWeatherData,
    ProviderSuccess,
)

OPEN_METEO_URL = 'https://api.open-meteo.com/v1/forecast'
OPEN_METEO_GEOCODING_URL = 'https://geocoding-api.open-meteo.com/v1/search'


def get_weather_by_position(
    lat: float,
    lon: float,
    location_name: str | None = None,
    timezone: str | None = None,
) -> ProviderSuccess:
    """查询 Open-Meteo 并返回标准化后的 provider 结果。"""

    raw_data = fetch_open_meteo_raw_weather(lat, lon, timezone=timezone)
    normalized = normalize_open_meteo_weather(
        raw_data,
        lat,
        lon,
        location_name=location_name,
        timezone=timezone,
    )
    return ProviderSuccess(provider='open-meteo', data=normalized)


def fetch_open_meteo_raw_weather(
    lat: float,
    lon: float,
    timezone: str | None = None,
) -> dict:
    """查询 Open-Meteo 原始天气数据。"""

    return http_get_json(
        OPEN_METEO_URL,
        label='Open-Meteo',
        timeout=15.0,
        params=_build_open_meteo_params(lat, lon, timezone),
        context={'lat': lat, 'lon': lon},
    )


def normalize_open_meteo_weather(
    raw_data: dict,
    lat: float,
    lon: float,
    location_name: str | None = None,
    timezone: str | None = None,
) -> NormalizedWeatherData:
    """将 Open-Meteo 原始响应映射为统一天气结构。"""

    current = raw_data.get('current', {})
    daily = raw_data.get('daily', {})
    hourly = raw_data.get('hourly', {})
    resolved_timezone = raw_data.get('timezone', timezone)

    return NormalizedWeatherData(
        location=LocationInfo(
            name=location_name,
            lat=lat,
            lon=lon,
            timezone=resolved_timezone,
        ),
        current=CurrentWeather(
            temperature_c=to_float(current.get('temperature_2m')),
            feels_like_c=to_float(current.get('apparent_temperature')),
            humidity=to_float(current.get('relative_humidity_2m')),
            wind_speed_kph=to_float(current.get('wind_speed_10m')),
            wind_direction_deg=to_float(current.get('wind_direction_10m')),
            pressure_hpa=to_float(current.get('pressure_msl')),
            visibility_km=_meters_to_km(current.get('visibility')),
            cloud_cover_percent=to_float(current.get('cloud_cover')),
            cloud_cover_low_percent=to_float(current.get('cloud_cover_low')),
            cloud_cover_mid_percent=to_float(current.get('cloud_cover_mid')),
            cloud_cover_high_percent=to_float(current.get('cloud_cover_high')),
            weather_code=map_open_meteo_weather_code(current.get('weather_code')),
            weather_text=_weather_text_from_open_meteo_code(current.get('weather_code')),
            observation_time=current.get('time'),
        ),
        daily=[
            DailyForecastItem(
                date=date,
                temp_min_c=_safe_index(daily.get('temperature_2m_min'), idx),
                temp_max_c=_safe_index(daily.get('temperature_2m_max'), idx),
                precipitation_probability=_percent_index_to_ratio(
                    daily.get('precipitation_probability_max'), idx
                ),
                cloud_cover_percent=_safe_index(daily.get('cloud_cover_mean'), idx),
                weather_code_day=map_open_meteo_weather_code(
                    _safe_index(daily.get('weather_code'), idx)
                ),
                weather_text_day=_weather_text_from_open_meteo_code(
                    _safe_index(daily.get('weather_code'), idx)
                ),
            )
            for idx, date in enumerate(daily.get('time', []))
        ],
        hourly=[
            HourlyForecastItem(
                time=time_value,
                temperature_c=_safe_index(hourly.get('temperature_2m'), idx),
                humidity=_safe_index(hourly.get('relative_humidity_2m'), idx),
                precipitation_probability=_percent_index_to_ratio(
                    hourly.get('precipitation_probability'), idx
                ),
                wind_speed_kph=_safe_index(hourly.get('wind_speed_10m'), idx),
                wind_direction_deg=_safe_index(hourly.get('wind_direction_10m'), idx),
                cloud_cover_percent=_safe_index(hourly.get('cloud_cover'), idx),
                cloud_cover_low_percent=_safe_index(hourly.get('cloud_cover_low'), idx),
                cloud_cover_mid_percent=_safe_index(hourly.get('cloud_cover_mid'), idx),
                cloud_cover_high_percent=_safe_index(hourly.get('cloud_cover_high'), idx),
                weather_code=map_open_meteo_weather_code(
                    _safe_index(hourly.get('weather_code'), idx)
                ),
                weather_text=_weather_text_from_open_meteo_code(
                    _safe_index(hourly.get('weather_code'), idx)
                ),
            )
            for idx, time_value in enumerate(hourly.get('time', []))
        ],
    )


def map_open_meteo_weather_code(code: int | None) -> str | None:
    """将 Open-Meteo 天气代码映射为内部统一 weather_code。"""

    if code is None:
        return None
    if code == 0:
        return 'clear'
    if code in {1, 2, 3, 45, 48}:
        return 'partly_cloudy'
    if code in {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82}:
        return 'rain'
    if code in {71, 73, 75, 77, 85, 86}:
        return 'snow'
    if code in {95, 96, 99}:
        return 'thunderstorm'
    return 'unknown'


def _build_open_meteo_params(lat: float, lon: float, timezone: str | None) -> dict:
    """构造 Open-Meteo 请求参数。"""

    return {
        'latitude': lat,
        'longitude': lon,
        'timezone': timezone or 'auto',
        'current': ','.join(
            [
                'temperature_2m',
                'apparent_temperature',
                'relative_humidity_2m',
                'wind_speed_10m',
                'wind_direction_10m',
                'pressure_msl',
                'visibility',
                'cloud_cover',
                'cloud_cover_low',
                'cloud_cover_mid',
                'cloud_cover_high',
                'weather_code',
            ]
        ),
        'hourly': ','.join(
            [
                'temperature_2m',
                'relative_humidity_2m',
                'precipitation_probability',
                'wind_speed_10m',
                'wind_direction_10m',
                'cloud_cover',
                'cloud_cover_low',
                'cloud_cover_mid',
                'cloud_cover_high',
                'weather_code',
            ]
        ),
        'daily': ','.join(
            [
                'temperature_2m_min',
                'temperature_2m_max',
                'precipitation_probability_max',
                'cloud_cover_mean',
                'weather_code',
            ]
        ),
    }


def _weather_text_from_open_meteo_code(code: int | None) -> str | None:
    """将 Open-Meteo 天气代码映射为简短文本。"""

    mapping = {
        0: 'Clear',
        1: 'Mainly clear',
        2: 'Partly cloudy',
        3: 'Overcast',
        45: 'Fog',
        48: 'Depositing rime fog',
        51: 'Light drizzle',
        53: 'Drizzle',
        55: 'Dense drizzle',
        61: 'Slight rain',
        63: 'Rain',
        65: 'Heavy rain',
        71: 'Slight snow',
        73: 'Snow',
        75: 'Heavy snow',
        80: 'Rain showers',
        81: 'Rain showers',
        82: 'Violent rain showers',
        95: 'Thunderstorm',
        96: 'Thunderstorm with hail',
        99: 'Thunderstorm with hail',
    }
    return mapping.get(code, 'Unknown') if code is not None else None


def _meters_to_km(value: int | float | None) -> float | None:
    """将米转换为千米。"""

    if value is None:
        return None
    return float(value) / 1000.0


def _safe_index(values: list | None, index: int) -> float | int | None:
    """安全读取数组中的指定位置。"""

    if values is None or index >= len(values):
        return None
    return values[index]


def _percent_index_to_ratio(values: list | None, index: int) -> float | None:
    """安全读取百分比数组并转换为 0 到 1 之间的小数。"""

    value = _safe_index(values, index)
    if value is None:
        return None
    return float(value) / 100.0


# ── Name-based weather ──────────────────────────────────────────────────


def get_weather_by_name(place_name: str) -> ProviderSuccess:
    """通过地点名称查询 Open-Meteo 天气（内部 geocoding + 天气）。"""

    result = _geocode_open_meteo(place_name)
    return get_weather_by_position(
        lat=result['lat'],
        lon=result['lon'],
        location_name=result['name'],
        timezone=result.get('timezone'),
    )


def _geocode_open_meteo(place_name: str) -> dict:
    """使用 Open-Meteo Geocoding API 解析地点名称为坐标。

    Returns:
        dict with keys: name, lat, lon, timezone (optional).

    Raises:
        MCPError: 网络错误或未找到地点。
    """

    data = http_get_json(
        OPEN_METEO_GEOCODING_URL,
        label='Open-Meteo 地理编码',
        timeout=10.0,
        params={
            'name': place_name,
            'count': 5,
            'language': 'zh',
            'format': 'json',
        },
        context={'place_name': place_name},
    )

    results = data.get('results') or []
    if not results:
        raise MCPError(
            MCPError.EXTERNAL_API_ERROR,
            f'Open-Meteo 地理编码未找到地点: {place_name}',
            {'place_name': place_name},
        )

    best = _select_best_geocode_result(results)
    return {
        'name': _build_open_meteo_location_name(best),
        'lat': float(best['latitude']),
        'lon': float(best['longitude']),
        'timezone': best.get('timezone'),
    }


def _select_best_geocode_result(results: list[dict]) -> dict:
    """从多条地理编码结果中选最优（省会 > 普通城市，人口多优先）。"""

    def _rank(result: dict) -> tuple[int, int]:
        feature = result.get('feature_code', '')
        is_ppla = 0 if feature == 'PPLA' else 1
        population = result.get('population') or 0
        return (is_ppla, -population)

    results.sort(key=_rank)
    return results[0]


def _build_open_meteo_location_name(result: dict) -> str:
    """从 Open-Meteo 地理编码结果构造可读地名。"""

    parts = []
    name = result.get('name', '')
    if name:
        parts.append(name)
    admin1 = result.get('admin1', '')
    if admin1:
        parts.append(admin1)
    country = result.get('country', '')
    if country:
        parts.append(country)
    return ', '.join(parts) if parts else name
