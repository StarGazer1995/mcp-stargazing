import os
from src.server_instance import mcp
from src.qweather_interaction import qweather_get_weather_by_name, qweather_get_weather_by_position

from src.response import format_response


def _get_qweather_auth_from_env() -> tuple[str | None, str | None, str | None]:
    """
    从环境变量读取 QWeather 鉴权与 Host 配置。

    优先级：
    - JWT：QWEATHER_JWT_TOKEN（推荐）
    - API KEY：QWEATHER_API_KEY（兼容旧用法）
    - API Host：QWEATHER_API_HOST（建议配置；不配会回退公共域名）
    """

    api_key = os.getenv("QWEATHER_API_KEY")
    jwt_token = os.getenv("QWEATHER_JWT_TOKEN")
    api_host = os.getenv("QWEATHER_API_HOST")
    if not api_key and not jwt_token:
        raise ValueError("QWEATHER_API_KEY 或 QWEATHER_JWT_TOKEN 环境变量未设置。")
    return api_key, jwt_token, api_host


@mcp.tool()
def get_weather_by_name(place_name: str):
    """
    通过地点名称获取天气（实时 + 10 天预报）。

    Args:
        place_name: 地点名称（例如城市/区县），会先进行 POI/位置搜索再查询天气。

    Returns:
        Dict，包含 keys: "data", "_meta"。

    Raises:
        ValueError: 未配置必要环境变量时抛出（QWEATHER_API_KEY 或 QWEATHER_JWT_TOKEN）。
    """
    api_key, jwt_token, api_host = _get_qweather_auth_from_env()
    try:
        # 兼容旧签名：第二个位置参数仍然传 api_key（若使用 JWT 则为 None）
        result = qweather_get_weather_by_name(
            place_name,
            api_key,
            api_host=api_host,
            jwt_token=jwt_token,
        )
        return format_response(result)
    except Exception as e:
        # fast failure：直接抛出异常，避免把 None 包装成 success
        raise ValueError(f"QWeather 请求失败: {e}") from e

@mcp.tool()
def get_weather_by_position(lat: float, lon: float):
    """
    通过经纬度获取天气（实时 + 10 天预报）。

    Args:
        lat: 纬度
        lon: 经度

    Returns:
        Dict，包含 keys: "data", "_meta"。

    Raises:
        ValueError: 未配置必要环境变量时抛出（QWEATHER_API_KEY 或 QWEATHER_JWT_TOKEN）。
    """
    api_key, jwt_token, api_host = _get_qweather_auth_from_env()
    try:
        result = qweather_get_weather_by_position(
            lat,
            lon,
            api_key,
            api_host=api_host,
            jwt_token=jwt_token,
        )
        return format_response(result)
    except Exception as e:
        raise ValueError(f"QWeather 请求失败: {e}") from e
