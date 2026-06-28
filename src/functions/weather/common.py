"""Shared utilities for weather providers."""

from typing import TYPE_CHECKING, Protocol

import requests

from src.response import MCPError

if TYPE_CHECKING:
    from src.schemas.weather import ProviderSuccess


class WeatherProvider(Protocol):
    """Protocol that every weather provider module must satisfy."""

    def get_weather_by_position(
        self,
        lat: float,
        lon: float,
        location_name: str | None = None,
        timezone: str | None = None,
    ) -> 'ProviderSuccess': ...

    def get_weather_by_name(self, place_name: str) -> 'ProviderSuccess': ...


# ── HTTP ─────────────────────────────────────────────────────────────────


def http_get_json(
    url: str,
    *,
    label: str,
    timeout: float = 15.0,
    params: dict | None = None,
    context: dict | None = None,
) -> dict:
    """HTTP GET 请求并将响应解析为 JSON。

    所有网络/HTTP/解析错误统一映射为 MCPError：
    - Timeout → API_TIMEOUT
    - ConnectionError → NETWORK_ERROR
    - HTTPError   → EXTERNAL_API_ERROR
    - 其他网络错误 → NETWORK_ERROR
    - JSON 解析失败 → EXTERNAL_API_ERROR

    Args:
        url: 请求 URL。
        label: 用于错误信息的人类可读标签（如 "Open-Meteo"）。
        timeout: 请求超时秒数。
        params: 可选的查询参数。
        context: 附加到错误 details 的上下文信息。
    """

    ctx = context or {}
    try:
        response = requests.get(url, params=params, timeout=timeout)
        response.raise_for_status()
    except requests.exceptions.Timeout as exc:
        raise MCPError(
            MCPError.API_TIMEOUT,
            f'{label} 请求超时。',
            ctx,
        ) from exc
    except requests.exceptions.ConnectionError as exc:
        raise MCPError(
            MCPError.NETWORK_ERROR,
            f'{label} 网络连接失败。',
            ctx,
        ) from exc
    except requests.exceptions.HTTPError as exc:
        raise MCPError(
            MCPError.EXTERNAL_API_ERROR,
            f'{label} 返回 HTTP {response.status_code}。',
            {**ctx, 'status_code': response.status_code},
        ) from exc
    except requests.exceptions.RequestException as exc:
        raise MCPError(
            MCPError.NETWORK_ERROR,
            f'{label} 请求失败: {exc}',
            ctx,
        ) from exc

    try:
        return response.json()
    except ValueError as exc:
        raise MCPError(
            MCPError.EXTERNAL_API_ERROR,
            f'{label} 返回了无效 JSON。',
            ctx,
        ) from exc


# ── Conversion helpers ────────────────────────────────────────────────────


def to_float(value: str | int | float | None) -> float | None:
    """将输入值安全转换为浮点数（None / 空字符串 / 非数字 → None）。"""

    if value in (None, ''):
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def to_ratio(value: str | int | float | None) -> float | None:
    """将百分比（0-100）转换为 0.0-1.0 的小数。"""

    numeric = to_float(value)
    if numeric is None:
        return None
    return numeric / 100.0
