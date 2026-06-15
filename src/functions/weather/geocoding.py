"""Shared geocoding helpers for weather tools."""

from geopy.exc import GeocoderServiceError, GeocoderTimedOut
from geopy.geocoders import Nominatim

from src.response import MCPError


def resolve_place_name(place_name: str) -> dict:
    """将地点名称解析为标准位置对象。"""

    cleaned_name = place_name.strip()
    if not cleaned_name:
        raise MCPError(
            MCPError.CONFIGURATION_ERROR,
            "place_name 不能为空。",
            {"place_name": place_name},
        )

    return _resolve_with_nominatim(cleaned_name)


def _resolve_with_nominatim(place_name: str) -> dict:
    """使用 Nominatim 地理编码服务解析地点名称。"""

    geocoder = Nominatim(user_agent="mcp-stargazing")
    try:
        result = geocoder.geocode(place_name, exactly_one=True, addressdetails=True)
    except GeocoderTimedOut as exc:
        raise MCPError(
            MCPError.API_TIMEOUT,
            f"地理编码请求超时: {place_name}",
            {"place_name": place_name},
        ) from exc
    except GeocoderServiceError as exc:
        raise MCPError(
            MCPError.NETWORK_ERROR,
            f"地理编码服务请求失败: {place_name}",
            {"place_name": place_name},
        ) from exc

    if result is None:
        raise MCPError(
            MCPError.EXTERNAL_API_ERROR,
            f"未找到地点: {place_name}",
            {"place_name": place_name},
        )

    display_name = getattr(result, "address", None) or place_name
    return normalize_geocoding_result(
        name=display_name,
        lat=float(result.latitude),
        lon=float(result.longitude),
        timezone=None,
    )


def normalize_geocoding_result(
    name: str,
    lat: float,
    lon: float,
    timezone: str | None = None,
) -> dict:
    """将地理编码结果标准化为统一位置结构。"""

    return {
        "name": name,
        "lat": lat,
        "lon": lon,
        "timezone": timezone,
    }
