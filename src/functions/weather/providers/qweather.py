"""QWeather provider adapter."""

import os

from src.functions.weather.common import to_float, to_ratio
from src.qweather_interaction import (
    qweather_get_poi,
    qweather_get_weather_by_coord_in_ten_days,
    qweather_get_weather_by_coord_in_twenty_four_hours,
    qweather_get_weather_by_coord_real_time,
)
from src.response import MCPError
from src.schemas.weather import (
    CurrentWeather,
    DailyForecastItem,
    HourlyForecastItem,
    LocationInfo,
    NormalizedWeatherData,
    ProviderSuccess,
)


def get_qweather_auth_from_env() -> tuple[str | None, str | None, str | None]:
    """从环境变量读取 QWeather 鉴权与 Host 配置。"""

    api_key = os.getenv('QWEATHER_API_KEY')
    jwt_token = os.getenv('QWEATHER_JWT_TOKEN')
    api_host = os.getenv('QWEATHER_API_HOST')
    if not api_key and not jwt_token:
        raise MCPError(
            MCPError.MISSING_API_KEY,
            'QWEATHER_API_KEY 或 QWEATHER_JWT_TOKEN 环境变量未设置。',
            {'required_vars': ['QWEATHER_API_KEY', 'QWEATHER_JWT_TOKEN']},
        )
    return api_key, jwt_token or None, api_host or None


def get_weather_by_position(
    lat: float,
    lon: float,
    location_name: str | None = None,
    timezone: str | None = None,
) -> ProviderSuccess:
    """查询 QWeather 并返回标准化后的 provider 结果。"""

    raw_data = fetch_qweather_raw_weather(lat, lon)
    normalized = normalize_qweather_weather(
        raw_data,
        lat,
        lon,
        location_name=location_name,
        timezone=timezone,
    )
    return ProviderSuccess(provider='qweather', data=normalized)


def fetch_qweather_raw_weather(lat: float, lon: float) -> dict:
    """查询 QWeather 原始天气数据。"""

    api_key, jwt_token, api_host = get_qweather_auth_from_env()
    return {
        'current': qweather_get_weather_by_coord_real_time(
            lon,
            lat,
            api_key,
            api_host=api_host,
            jwt_token=jwt_token,
        ),
        'daily': qweather_get_weather_by_coord_in_ten_days(
            lon,
            lat,
            api_key,
            api_host=api_host,
            jwt_token=jwt_token,
        ),
        'hourly': qweather_get_weather_by_coord_in_twenty_four_hours(
            lon,
            lat,
            api_key,
            api_host=api_host,
            jwt_token=jwt_token,
        ),
    }


def normalize_qweather_weather(
    raw_data: dict,
    lat: float,
    lon: float,
    location_name: str | None = None,
    timezone: str | None = None,
) -> NormalizedWeatherData:
    """将 QWeather 原始响应映射为统一天气结构。"""

    current = raw_data.get('current', {}).get('now', {})
    daily_rows = raw_data.get('daily', {}).get('daily', [])
    hourly_rows = raw_data.get('hourly', {}).get('hourly', [])

    return NormalizedWeatherData(
        location=LocationInfo(
            name=location_name,
            lat=lat,
            lon=lon,
            timezone=timezone,
        ),
        current=CurrentWeather(
            temperature_c=to_float(current.get('temp')),
            feels_like_c=to_float(current.get('feelsLike')),
            humidity=to_float(current.get('humidity')),
            wind_speed_kph=to_float(current.get('windSpeed')),
            wind_direction_deg=to_float(current.get('wind360')),
            pressure_hpa=to_float(current.get('pressure')),
            visibility_km=to_float(current.get('vis')),
            cloud_cover_percent=to_float(current.get('cloud')),
            cloud_cover_low_percent=None,
            cloud_cover_mid_percent=None,
            cloud_cover_high_percent=None,
            weather_code=map_qweather_condition_code(current.get('icon')),
            weather_text=current.get('text'),
            observation_time=current.get('obsTime'),
        ),
        daily=[
            DailyForecastItem(
                date=row.get('fxDate'),
                temp_min_c=to_float(row.get('tempMin')),
                temp_max_c=to_float(row.get('tempMax')),
                precipitation_probability=to_ratio(row.get('precip')),
                cloud_cover_percent=to_float(row.get('cloud')),
                weather_code_day=map_qweather_condition_code(row.get('iconDay')),
                weather_text_day=row.get('textDay'),
            )
            for row in daily_rows
            if row.get('fxDate')
        ],
        hourly=[
            HourlyForecastItem(
                time=row.get('fxTime'),
                temperature_c=to_float(row.get('temp')),
                humidity=to_float(row.get('humidity')),
                precipitation_probability=to_ratio(row.get('pop')),
                wind_speed_kph=to_float(row.get('windSpeed')),
                wind_direction_deg=to_float(row.get('wind360')),
                cloud_cover_percent=to_float(row.get('cloud')),
                cloud_cover_low_percent=None,
                cloud_cover_mid_percent=None,
                cloud_cover_high_percent=None,
                weather_code=map_qweather_condition_code(row.get('icon')),
                weather_text=row.get('text'),
            )
            for row in hourly_rows
            if row.get('fxTime')
        ],
    )


def map_qweather_condition_code(code: str | None) -> str | None:
    """将 QWeather 天气代码映射为内部统一 weather_code。"""

    if code is None:
        return None

    cloudy_codes = {'100', '101', '102', '103', '104'}
    rain_codes = {
        '300',
        '301',
        '302',
        '303',
        '304',
        '305',
        '306',
        '307',
        '308',
        '309',
        '310',
        '311',
        '312',
        '313',
        '314',
        '315',
        '316',
        '317',
        '318',
        '350',
        '351',
        '399',
    }
    snow_codes = {
        '400',
        '401',
        '402',
        '403',
        '404',
        '405',
        '406',
        '407',
        '408',
        '409',
        '410',
        '456',
        '457',
        '499',
    }
    fog_codes = {
        '500',
        '501',
        '502',
        '503',
        '504',
        '507',
        '508',
        '509',
        '510',
        '511',
        '512',
        '513',
        '514',
        '515',
    }

    if code == '100':
        return 'clear'
    if code in cloudy_codes:
        return 'partly_cloudy'
    if code in rain_codes:
        return 'rain'
    if code in snow_codes:
        return 'snow'
    if code in fog_codes:
        return 'fog'
    return 'unknown'


# ── Name-based weather ──────────────────────────────────────────────────


def get_weather_by_name(place_name: str) -> ProviderSuccess:
    """通过地点名称查询 QWeather 天气（内部 POI geocoding + 天气）。"""

    api_key, jwt_token, api_host = get_qweather_auth_from_env()

    poi_result = qweather_get_poi(
        place_name,
        api_key,
        api_host=api_host,
        jwt_token=jwt_token,
    )
    if not poi_result or not poi_result.get('poi'):
        raise MCPError(
            MCPError.EXTERNAL_API_ERROR,
            f'QWeather POI 未找到地点: {place_name}',
            {'place_name': place_name},
        )

    first_poi = poi_result['poi'][0]
    lat = float(first_poi['lat'])
    lon = float(first_poi['lon'])
    location_name = first_poi.get('name') or place_name

    raw_data = fetch_qweather_raw_weather(lat, lon)
    normalized = normalize_qweather_weather(
        raw_data,
        lat,
        lon,
        location_name=location_name,
        timezone=None,
    )
    return ProviderSuccess(provider='qweather', data=normalized)
