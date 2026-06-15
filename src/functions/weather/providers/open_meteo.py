"""Open-Meteo provider adapter."""

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

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


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
    return ProviderSuccess(provider="open-meteo", data=normalized)


def build_open_meteo_url(
    lat: float,
    lon: float,
    timezone: str | None = None,
) -> str:
    """构造 Open-Meteo 请求 URL。"""

    request = requests.Request("GET", OPEN_METEO_URL, params=_build_open_meteo_params(lat, lon, timezone))
    prepared = request.prepare()
    if prepared.url is None:
        raise MCPError(
            MCPError.CONFIGURATION_ERROR,
            "Open-Meteo 请求 URL 构造失败。",
            {"lat": lat, "lon": lon},
        )
    return prepared.url


def fetch_open_meteo_raw_weather(
    lat: float,
    lon: float,
    timezone: str | None = None,
) -> dict:
    """查询 Open-Meteo 原始天气数据。"""

    try:
        response = requests.get(
            OPEN_METEO_URL,
            params=_build_open_meteo_params(lat, lon, timezone),
            timeout=15.0,
        )
        response.raise_for_status()
    except requests.exceptions.Timeout as exc:
        raise MCPError(
            MCPError.API_TIMEOUT,
            "Open-Meteo 请求超时。",
            {"lat": lat, "lon": lon},
        ) from exc
    except requests.exceptions.ConnectionError as exc:
        raise MCPError(
            MCPError.NETWORK_ERROR,
            "Open-Meteo 网络连接失败。",
            {"lat": lat, "lon": lon},
        ) from exc
    except requests.exceptions.HTTPError as exc:
        raise MCPError(
            MCPError.EXTERNAL_API_ERROR,
            f"Open-Meteo 返回 HTTP {response.status_code}。",
            {"lat": lat, "lon": lon, "status_code": response.status_code},
        ) from exc
    except requests.exceptions.RequestException as exc:
        raise MCPError(
            MCPError.NETWORK_ERROR,
            f"Open-Meteo 请求失败: {exc}",
            {"lat": lat, "lon": lon},
        ) from exc

    try:
        return response.json()
    except ValueError as exc:
        raise MCPError(
            MCPError.EXTERNAL_API_ERROR,
            "Open-Meteo 返回了无效 JSON。",
            {"lat": lat, "lon": lon},
        ) from exc


def normalize_open_meteo_weather(
    raw_data: dict,
    lat: float,
    lon: float,
    location_name: str | None = None,
    timezone: str | None = None,
) -> NormalizedWeatherData:
    """将 Open-Meteo 原始响应映射为统一天气结构。"""

    current = raw_data.get("current", {})
    daily = raw_data.get("daily", {})
    hourly = raw_data.get("hourly", {})
    resolved_timezone = raw_data.get("timezone", timezone)

    return NormalizedWeatherData(
        location=LocationInfo(
            name=location_name,
            lat=lat,
            lon=lon,
            timezone=resolved_timezone,
        ),
        current=CurrentWeather(
            temperature_c=_to_float(current.get("temperature_2m")),
            feels_like_c=_to_float(current.get("apparent_temperature")),
            humidity=_to_float(current.get("relative_humidity_2m")),
            wind_speed_kph=_to_float(current.get("wind_speed_10m")),
            wind_direction_deg=_to_float(current.get("wind_direction_10m")),
            pressure_hpa=_to_float(current.get("pressure_msl")),
            visibility_km=_meters_to_km(current.get("visibility")),
            cloud_cover_percent=_to_float(current.get("cloud_cover")),
            cloud_cover_low_percent=_to_float(current.get("cloud_cover_low")),
            cloud_cover_mid_percent=_to_float(current.get("cloud_cover_mid")),
            cloud_cover_high_percent=_to_float(current.get("cloud_cover_high")),
            weather_code=map_open_meteo_weather_code(current.get("weather_code")),
            weather_text=_weather_text_from_open_meteo_code(current.get("weather_code")),
            observation_time=current.get("time"),
        ),
        daily=[
            DailyForecastItem(
                date=date,
                temp_min_c=_safe_index(daily.get("temperature_2m_min"), idx),
                temp_max_c=_safe_index(daily.get("temperature_2m_max"), idx),
                precipitation_probability=_percent_index_to_ratio(daily.get("precipitation_probability_max"), idx),
                cloud_cover_percent=_safe_index(daily.get("cloud_cover_mean"), idx),
                weather_code_day=map_open_meteo_weather_code(_safe_index(daily.get("weather_code"), idx)),
                weather_text_day=_weather_text_from_open_meteo_code(_safe_index(daily.get("weather_code"), idx)),
            )
            for idx, date in enumerate(daily.get("time", []))
        ],
        hourly=[
            HourlyForecastItem(
                time=time_value,
                temperature_c=_safe_index(hourly.get("temperature_2m"), idx),
                humidity=_safe_index(hourly.get("relative_humidity_2m"), idx),
                precipitation_probability=_percent_index_to_ratio(hourly.get("precipitation_probability"), idx),
                wind_speed_kph=_safe_index(hourly.get("wind_speed_10m"), idx),
                wind_direction_deg=_safe_index(hourly.get("wind_direction_10m"), idx),
                cloud_cover_percent=_safe_index(hourly.get("cloud_cover"), idx),
                cloud_cover_low_percent=_safe_index(hourly.get("cloud_cover_low"), idx),
                cloud_cover_mid_percent=_safe_index(hourly.get("cloud_cover_mid"), idx),
                cloud_cover_high_percent=_safe_index(hourly.get("cloud_cover_high"), idx),
                weather_code=map_open_meteo_weather_code(_safe_index(hourly.get("weather_code"), idx)),
                weather_text=_weather_text_from_open_meteo_code(_safe_index(hourly.get("weather_code"), idx)),
            )
            for idx, time_value in enumerate(hourly.get("time", []))
        ],
    )


def map_open_meteo_weather_code(code: int | None) -> str | None:
    """将 Open-Meteo 天气代码映射为内部统一 weather_code。"""

    if code is None:
        return None
    if code == 0:
        return "clear"
    if code in {1, 2, 3, 45, 48}:
        return "partly_cloudy"
    if code in {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82}:
        return "rain"
    if code in {71, 73, 75, 77, 85, 86}:
        return "snow"
    if code in {95, 96, 99}:
        return "thunderstorm"
    return "unknown"


def _build_open_meteo_params(lat: float, lon: float, timezone: str | None) -> dict:
    """构造 Open-Meteo 请求参数。"""

    return {
        "latitude": lat,
        "longitude": lon,
        "timezone": timezone or "auto",
        "current": ",".join([
            "temperature_2m",
            "apparent_temperature",
            "relative_humidity_2m",
            "wind_speed_10m",
            "wind_direction_10m",
            "pressure_msl",
            "visibility",
            "cloud_cover",
            "cloud_cover_low",
            "cloud_cover_mid",
            "cloud_cover_high",
            "weather_code",
        ]),
        "hourly": ",".join([
            "temperature_2m",
            "relative_humidity_2m",
            "precipitation_probability",
            "wind_speed_10m",
            "wind_direction_10m",
            "cloud_cover",
            "cloud_cover_low",
            "cloud_cover_mid",
            "cloud_cover_high",
            "weather_code",
        ]),
        "daily": ",".join([
            "temperature_2m_min",
            "temperature_2m_max",
            "precipitation_probability_max",
            "cloud_cover_mean",
            "weather_code",
        ]),
    }


def _weather_text_from_open_meteo_code(code: int | None) -> str | None:
    """将 Open-Meteo 天气代码映射为简短文本。"""

    mapping = {
        0: "Clear",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Fog",
        48: "Depositing rime fog",
        51: "Light drizzle",
        53: "Drizzle",
        55: "Dense drizzle",
        61: "Slight rain",
        63: "Rain",
        65: "Heavy rain",
        71: "Slight snow",
        73: "Snow",
        75: "Heavy snow",
        80: "Rain showers",
        81: "Rain showers",
        82: "Violent rain showers",
        95: "Thunderstorm",
        96: "Thunderstorm with hail",
        99: "Thunderstorm with hail",
    }
    return mapping.get(code, "Unknown") if code is not None else None


def _to_float(value: int | float | None) -> float | None:
    """将输入值安全转换为浮点数。"""

    if value is None:
        return None
    return float(value)


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
