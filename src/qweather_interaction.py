"""
和风天气（QWeather）API 客户端封装。

说明：
- 从官方文档 2026 年起公共域名将逐步停止服务，推荐使用你账号专属的 API Host。
- 本模块支持两种鉴权：JWT（推荐）与 API KEY（兼容旧用法）。
- 默认启用“fast failure”：关键配置缺失或 API 返回非 200 会直接抛错，尽早暴露问题。
"""

from src.functions.weather.providers._http import fetch_qweather_json, get_qweather_api_host


def qweather_get_poi(
    position: str,
    api_token: str | None,
    *,
    api_host: str | None = None,
    jwt_token: str | None = None,
) -> dict | None:
    """根据地名关键词查询 POI（默认查询 scenic 类型）。"""

    # 文档：/geo/v2/poi/lookup
    host = (api_host or get_qweather_api_host('geoapi.qweather.com')).strip().rstrip('/')
    api = f'https://{host}/geo/v2/poi/lookup?type=scenic&location={position}'
    return fetch_qweather_json(api, api_token, jwt_token=jwt_token)


def qweather_get_weather_by_coord_real_time(
    lon: float,
    lat: float,
    api_token: str | None,
    *,
    api_host: str | None = None,
    jwt_token: str | None = None,
) -> dict | None:
    """根据经纬度获取实时天气。"""

    host = (api_host or get_qweather_api_host('api.qweather.com')).strip().rstrip('/')
    api = f'https://{host}/v7/weather/now?location={lon},{lat}'
    return fetch_qweather_json(api, api_token, jwt_token=jwt_token)


def qweather_get_weather_by_coord_in_ten_days(
    lon: float,
    lat: float,
    api_token: str | None,
    *,
    api_host: str | None = None,
    jwt_token: str | None = None,
) -> dict | None:
    """根据经纬度获取 10 天预报。"""

    host = (api_host or get_qweather_api_host('api.qweather.com')).strip().rstrip('/')
    api = f'https://{host}/v7/weather/10d?location={lon},{lat}'
    return fetch_qweather_json(api, api_token, jwt_token=jwt_token)


def qweather_get_weather_by_coord_in_twenty_four_hours(
    lon: float,
    lat: float,
    api_token: str | None,
    *,
    api_host: str | None = None,
    jwt_token: str | None = None,
) -> dict | None:
    """根据经纬度获取 24 小时逐小时预报。"""

    host = (api_host or get_qweather_api_host('api.qweather.com')).strip().rstrip('/')
    api = f'https://{host}/v7/weather/24h?location={lon},{lat}'
    return fetch_qweather_json(api, api_token, jwt_token=jwt_token)


def qweather_get_weather_by_name(
    city: str,
    api_token: str | None,
    *,
    api_host: str | None = None,
    jwt_token: str | None = None,
) -> dict | None:
    """
    根据城市名称获取天气（实时 + 10 天预报）。

    说明：QWeather 天气接口通常需要 LocationID 或经纬度，这里通过 POI 搜索取到坐标再请求天气数据。
    """

    res = qweather_get_poi(city, api_token, api_host=api_host, jwt_token=jwt_token)
    if not res:
        return None

    lat, lon = res['poi'][0]['lat'], res['poi'][0]['lon']

    real_time_data = qweather_get_weather_by_coord_real_time(
        lon, lat, api_token, api_host=api_host, jwt_token=jwt_token
    )
    ten_days_forcasts = qweather_get_weather_by_coord_in_ten_days(
        lon, lat, api_token, api_host=api_host, jwt_token=jwt_token
    )

    return {'real_time': real_time_data, 'ten_days_forcasts': ten_days_forcasts}


def qweather_get_weather_by_position(
    lat: float,
    lon: float,
    api_token: str | None,
    *,
    api_host: str | None = None,
    jwt_token: str | None = None,
) -> dict | None:
    """根据经纬度获取天气（实时 + 10 天预报）。"""

    real_time_data = qweather_get_weather_by_coord_real_time(
        lon, lat, api_token, api_host=api_host, jwt_token=jwt_token
    )
    ten_days_forcasts = qweather_get_weather_by_coord_in_ten_days(
        lon, lat, api_token, api_host=api_host, jwt_token=jwt_token
    )

    return {'real_time': real_time_data, 'ten_days_forcasts': ten_days_forcasts}
