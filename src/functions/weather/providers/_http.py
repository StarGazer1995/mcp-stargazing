"""Shared HTTP helpers for weather providers."""

import os
from collections.abc import Mapping
from typing import Any

import requests

from src.response import MCPError


def build_qweather_headers(api_key: str | None, jwt_token: str | None) -> dict[str, str]:
    """Build QWeather auth headers for either JWT or API key mode."""
    headers: dict[str, str] = {'Accept-Encoding': 'gzip'}
    if jwt_token:
        headers['Authorization'] = f'Bearer {jwt_token}'
        return headers
    if api_key:
        headers['X-QW-Api-Key'] = api_key
        return headers
    raise MCPError(
        MCPError.MISSING_API_KEY,
        '必须提供 api_key 或 jwt_token 之一用于访问 QWeather API。',
        {'provided': {'api_key': api_key is not None, 'jwt_token': jwt_token is not None}},
    )


def get_qweather_api_host(default_public_host: str) -> str:
    """Resolve the QWeather host, failing fast unless public fallback is enabled."""
    api_host = os.getenv('QWEATHER_API_HOST')
    if api_host:
        return api_host.strip().rstrip('/')

    allow_public = os.getenv('QWEATHER_ALLOW_PUBLIC_HOST', '').strip() in {
        '1',
        'true',
        'True',
        'yes',
        'YES',
    }
    if allow_public:
        return default_public_host

    raise MCPError(
        MCPError.CONFIGURATION_ERROR,
        '未设置 QWEATHER_API_HOST（账号专属 API Host）。'
        '为尽早暴露配置问题，本项目默认不再自动回退公共域名；'
        '如需临时兼容旧域名，请设置 QWEATHER_ALLOW_PUBLIC_HOST=1。',
        {'env_vars_checked': ['QWEATHER_API_HOST', 'QWEATHER_ALLOW_PUBLIC_HOST']},
    )


def fetch_weather_json(
    url: str,
    *,
    service_name: str,
    context: dict[str, Any],
    params: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
    timeout_s: float = 15.0,
    auth_failure_message: str | None = None,
    rate_limit_message: str | None = None,
) -> dict[str, Any]:
    """Fetch JSON from an external weather API and normalize transport errors."""
    response: requests.Response | None = None
    try:
        response = requests.get(url, params=params, headers=headers, timeout=timeout_s)
        response.raise_for_status()
    except requests.exceptions.Timeout as exc:
        raise MCPError(
            MCPError.API_TIMEOUT,
            f'{service_name} 请求超时。',
            {**context, 'timeout_seconds': timeout_s},
        ) from exc
    except requests.exceptions.ConnectionError as exc:
        raise MCPError(
            MCPError.NETWORK_ERROR,
            f'{service_name} 网络连接失败。',
            context,
        ) from exc
    except requests.exceptions.HTTPError as exc:
        status_code = response.status_code if response is not None else None
        if status_code == 401 and auth_failure_message is not None:
            raise MCPError(
                MCPError.API_AUTH_FAILURE,
                auth_failure_message,
                {**context, 'status_code': status_code},
            ) from exc
        if status_code == 429 and rate_limit_message is not None:
            raise MCPError(
                MCPError.API_RATE_LIMIT,
                rate_limit_message,
                {**context, 'status_code': status_code},
            ) from exc
        raise MCPError(
            MCPError.EXTERNAL_API_ERROR,
            f'{service_name} 返回 HTTP {status_code}。',
            {**context, 'status_code': status_code},
        ) from exc
    except requests.exceptions.RequestException as exc:
        raise MCPError(
            MCPError.NETWORK_ERROR,
            f'{service_name} 请求失败: {exc}',
            context,
        ) from exc

    try:
        return response.json()
    except ValueError as exc:
        raise MCPError(
            MCPError.EXTERNAL_API_ERROR,
            f'{service_name} 返回了无效 JSON。',
            context,
        ) from exc


def fetch_qweather_json(
    api_url: str,
    api_key: str | None = None,
    *,
    jwt_token: str | None = None,
    timeout_s: float = 15.0,
) -> dict[str, Any]:
    """Fetch a QWeather JSON payload and validate the provider-specific code field."""
    data = fetch_weather_json(
        api_url,
        service_name='QWeather API',
        context={'url': api_url},
        headers=build_qweather_headers(api_key=api_key, jwt_token=jwt_token),
        timeout_s=timeout_s,
        auth_failure_message='QWeather API authentication failed',
        rate_limit_message='QWeather API rate limit exceeded',
    )
    code = str(data.get('code', ''))
    if code and code != '200':
        raise MCPError(
            MCPError.EXTERNAL_API_ERROR,
            f'QWeather API returned error code {code}',
            {'url': api_url, 'api_code': code, 'response': data},
        )
    return data
