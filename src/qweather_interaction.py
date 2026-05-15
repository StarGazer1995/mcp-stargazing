"""
和风天气（QWeather）API 客户端封装。

说明：
- 从官方文档 2026 年起公共域名将逐步停止服务，推荐使用你账号专属的 API Host。
- 本模块支持两种鉴权：JWT（推荐）与 API KEY（兼容旧用法）。
- 默认启用“fast failure”：关键配置缺失或 API 返回非 200 会直接抛错，尽早暴露问题。
"""

import os

import requests
from src.response import MCPError
def _build_qweather_headers(api_key: str | None, jwt_token: str | None) -> dict:
    """构建 QWeather 请求 Headers（支持 JWT / API KEY）。"""

    headers: dict[str, str] = {"Accept-Encoding": "gzip"}
    if jwt_token:
        headers["Authorization"] = f"Bearer {jwt_token}"
    elif api_key:
        headers["X-QW-Api-Key"] = api_key
    else:
        raise MCPError(
            MCPError.MISSING_API_KEY,
            "必须提供 api_key 或 jwt_token 之一用于访问 QWeather API。",
            {"provided": {"api_key": api_key is not None, "jwt_token": jwt_token is not None}}
        )
    return headers


def _get_api_host_or_fail(default_public_host: str) -> str:
    """
    获取 API Host（fast failure）。

    规则：
    - 默认必须提供 `QWEATHER_API_HOST`，否则抛出异常；
    - 如确需沿用公共域名，显式设置 `QWEATHER_ALLOW_PUBLIC_HOST=1` 允许回退。
    """

    api_host = os.getenv("QWEATHER_API_HOST")
    if api_host:
        return api_host.strip().rstrip("/")

    allow_public = os.getenv("QWEATHER_ALLOW_PUBLIC_HOST", "").strip() in {"1", "true", "True", "yes", "YES"}
    if allow_public:
        return default_public_host

    raise MCPError(
        MCPError.CONFIGURATION_ERROR,
        "未设置 QWEATHER_API_HOST（账号专属 API Host）。"
        "为尽早暴露配置问题，本项目默认不再自动回退公共域名；"
        "如需临时兼容旧域名，请设置 QWEATHER_ALLOW_PUBLIC_HOST=1。",
        {"env_vars_checked": ["QWEATHER_API_HOST", "QWEATHER_ALLOW_PUBLIC_HOST"]}
    )


def fetch_gzipped_json(
    api_url: str,
    api_token: str | None = None,
    *,
    jwt_token: str | None = None,
    timeout_s: float = 15.0,
) -> dict | None:
    """
    请求 QWeather API 并返回 JSON（响应可能为 gzip 压缩，但 requests 会自动解压）。

    Args:
        api_url: 完整请求 URL。
        api_token: 兼容旧用法的 API KEY（推荐改用 jwt_token 或明确传入 api_key）。
        jwt_token: JWT Token（推荐），将以 `Authorization: Bearer ...` 发送。
        timeout_s: 请求超时时间（秒）。

    Returns:
        成功返回 dict；失败会抛出异常（fast failure）。
    """

    headers = _build_qweather_headers(api_key=api_token, jwt_token=jwt_token)
    try:
        response = requests.get(api_url, headers=headers, timeout=timeout_s)
        response.raise_for_status()
    except requests.exceptions.Timeout as e:
        raise MCPError(
            MCPError.API_TIMEOUT,
            f"QWeather API request timed out after {timeout_s} seconds",
            {"url": api_url, "timeout_seconds": timeout_s}
        ) from e
    except requests.exceptions.ConnectionError as e:
        raise MCPError(
            MCPError.NETWORK_ERROR,
            f"Network connection error while accessing QWeather API",
            {"url": api_url}
        ) from e
    except requests.exceptions.HTTPError as e:
        if response.status_code == 401:
            raise MCPError(
                MCPError.API_AUTH_FAILURE,
                "QWeather API authentication failed",
                {"url": api_url, "status_code": response.status_code}
            ) from e
        elif response.status_code == 429:
            raise MCPError(
                MCPError.API_RATE_LIMIT,
                "QWeather API rate limit exceeded",
                {"url": api_url, "status_code": response.status_code}
            ) from e
        else:
            raise MCPError(
                MCPError.EXTERNAL_API_ERROR,
                f"QWeather API returned HTTP {response.status_code}",
                {"url": api_url, "status_code": response.status_code}
            ) from e
    except requests.exceptions.RequestException as e:
        raise MCPError(
            MCPError.NETWORK_ERROR,
            f"Request error while accessing QWeather API: {e}",
            {"url": api_url}
        ) from e

    try:
        data = response.json()
    except ValueError as e:
        raise MCPError(
            MCPError.EXTERNAL_API_ERROR,
            "QWeather API returned invalid JSON response",
            {"url": api_url}
        ) from e

    # QWeather 响应通常包含 code 字段，200 表示成功
    code = str(data.get("code", ""))
    if code and code != "200":
        raise MCPError(
            MCPError.EXTERNAL_API_ERROR,
            f"QWeather API returned error code {code}",
            {"url": api_url, "api_code": code, "response": data}
        )
    return data
    
def qweather_get_poi(
    position: str,
    api_token: str | None,
    *,
    api_host: str | None = None,
    jwt_token: str | None = None,
) -> dict | None:
    """根据地名关键词查询 POI（默认查询 scenic 类型）。"""

    # 文档：/geo/v2/poi/lookup
    host = (api_host or _get_api_host_or_fail("geoapi.qweather.com")).strip().rstrip("/")
    api = f"https://{host}/geo/v2/poi/lookup?type=scenic&location={position}"
    return fetch_gzipped_json(api, api_token, jwt_token=jwt_token)

def qweather_get_weather_by_coord_real_time(
    lon: float,
    lat: float,
    api_token: str | None,
    *,
    api_host: str | None = None,
    jwt_token: str | None = None,
) -> dict | None:
    """根据经纬度获取实时天气。"""

    host = (api_host or _get_api_host_or_fail("api.qweather.com")).strip().rstrip("/")
    api = f"https://{host}/v7/weather/now?location={lon},{lat}"
    return fetch_gzipped_json(api, api_token, jwt_token=jwt_token)

def qweather_get_weather_by_coord_in_ten_days(
    lon: float,
    lat: float,
    api_token: str | None,
    *,
    api_host: str | None = None,
    jwt_token: str | None = None,
) -> dict | None:
    """根据经纬度获取 10 天预报。"""

    host = (api_host or _get_api_host_or_fail("api.qweather.com")).strip().rstrip("/")
    api = f"https://{host}/v7/weather/10d?location={lon},{lat}"
    return fetch_gzipped_json(api, api_token, jwt_token=jwt_token)

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
    
    return {
        "real_time": real_time_data,
        "ten_days_forcasts": ten_days_forcasts
    }

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

    return {
        "real_time": real_time_data,
        "ten_days_forcasts": ten_days_forcasts
    }
