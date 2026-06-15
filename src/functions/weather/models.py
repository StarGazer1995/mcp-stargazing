"""Shared payload builders for aggregated weather responses."""


def build_location_payload(
    name: str | None,
    lat: float,
    lon: float,
    timezone: str | None,
) -> dict:
    """构造统一的位置数据结构。"""

    return {
        "name": name,
        "lat": lat,
        "lon": lon,
        "timezone": timezone,
    }


def build_current_weather_payload(
    temperature_c: float | None = None,
    feels_like_c: float | None = None,
    humidity: float | None = None,
    wind_speed_kph: float | None = None,
    wind_direction_deg: float | None = None,
    pressure_hpa: float | None = None,
    visibility_km: float | None = None,
    cloud_cover_percent: float | None = None,
    cloud_cover_low_percent: float | None = None,
    cloud_cover_mid_percent: float | None = None,
    cloud_cover_high_percent: float | None = None,
    weather_code: str | None = None,
    weather_text: str | None = None,
    observation_time: str | None = None,
) -> dict:
    """构造统一的当前天气数据结构。"""

    return {
        "temperature_c": temperature_c,
        "feels_like_c": feels_like_c,
        "humidity": humidity,
        "wind_speed_kph": wind_speed_kph,
        "wind_direction_deg": wind_direction_deg,
        "pressure_hpa": pressure_hpa,
        "visibility_km": visibility_km,
        "cloud_cover_percent": cloud_cover_percent,
        "cloud_cover_low_percent": cloud_cover_low_percent,
        "cloud_cover_mid_percent": cloud_cover_mid_percent,
        "cloud_cover_high_percent": cloud_cover_high_percent,
        "weather_code": weather_code,
        "weather_text": weather_text,
        "observation_time": observation_time,
    }


def build_daily_forecast_item(
    date: str,
    temp_min_c: float | None = None,
    temp_max_c: float | None = None,
    precipitation_probability: float | None = None,
    cloud_cover_percent: float | None = None,
    weather_code_day: str | None = None,
    weather_text_day: str | None = None,
) -> dict:
    """构造统一的单日预报数据结构。"""

    return {
        "date": date,
        "temp_min_c": temp_min_c,
        "temp_max_c": temp_max_c,
        "precipitation_probability": precipitation_probability,
        "cloud_cover_percent": cloud_cover_percent,
        "weather_code_day": weather_code_day,
        "weather_text_day": weather_text_day,
    }


def build_hourly_forecast_item(
    time: str,
    temperature_c: float | None = None,
    humidity: float | None = None,
    precipitation_probability: float | None = None,
    wind_speed_kph: float | None = None,
    wind_direction_deg: float | None = None,
    cloud_cover_percent: float | None = None,
    cloud_cover_low_percent: float | None = None,
    cloud_cover_mid_percent: float | None = None,
    cloud_cover_high_percent: float | None = None,
    weather_code: str | None = None,
    weather_text: str | None = None,
) -> dict:
    """构造统一的单小时预报数据结构。"""

    return {
        "time": time,
        "temperature_c": temperature_c,
        "humidity": humidity,
        "precipitation_probability": precipitation_probability,
        "wind_speed_kph": wind_speed_kph,
        "wind_direction_deg": wind_direction_deg,
        "cloud_cover_percent": cloud_cover_percent,
        "cloud_cover_low_percent": cloud_cover_low_percent,
        "cloud_cover_mid_percent": cloud_cover_mid_percent,
        "cloud_cover_high_percent": cloud_cover_high_percent,
        "weather_code": weather_code,
        "weather_text": weather_text,
    }


def build_provider_success_payload(provider_name: str, data: dict) -> dict:
    """构造 provider 成功状态结果。"""

    return {
        "status": "success",
        "provider": provider_name,
        "data": data,
    }


def build_provider_error_payload(
    provider_name: str,
    code: str,
    message: str,
    details: dict | None = None,
) -> dict:
    """构造 provider 失败状态结果。"""

    error = {
        "code": code,
        "message": message,
    }
    if details:
        error["details"] = details
    return {
        "status": "error",
        "provider": provider_name,
        "error": error,
    }


def build_aggregated_weather_payload(
    location: dict,
    summary: dict,
    providers: dict,
    source: dict,
) -> dict:
    """构造最终综合天气响应数据结构。"""

    return {
        "location": location,
        "summary": summary,
        "providers": providers,
        "source": source,
    }
