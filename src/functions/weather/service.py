"""Aggregation service for multi-provider weather queries."""

from src.functions.weather.geocoding import resolve_place_name
from src.functions.weather.models import (
    build_aggregated_weather_payload,
    build_current_weather_payload,
    build_location_payload,
    build_provider_error_payload,
)
from src.functions.weather.providers import open_meteo, qweather, wttr
from src.response import MCPError

PROVIDER_ORDER = ["open-meteo", "qweather", "wttr"]


def get_aggregated_weather_by_name(
    place_name: str,
    provider: str = "all",
) -> dict:
    """根据地点名称查询并聚合多个天气提供商的结果。"""

    location = resolve_place_name(place_name)
    return get_aggregated_weather_by_position(
        location["lat"],
        location["lon"],
        provider=provider,
        location_name=location.get("name"),
        timezone=location.get("timezone"),
    )


def get_aggregated_weather_by_position(
    lat: float,
    lon: float,
    provider: str = "all",
    location_name: str | None = None,
    timezone: str | None = None,
) -> dict:
    """根据经纬度查询并聚合多个天气提供商的结果。"""

    provider_names = get_enabled_providers(provider)
    provider_results = query_providers_by_position(
        lat,
        lon,
        provider_names,
        location_name=location_name,
        timezone=timezone,
    )
    _ensure_any_provider_success(provider_results)

    successful_provider_data = [
        {"provider": result["provider"], "data": result["data"]}
        for result in provider_results.values()
        if result["status"] == "success"
    ]
    location_payload = _build_location(lat, lon, location_name, timezone, successful_provider_data)
    summary = _build_summary(successful_provider_data)
    source = _build_source_meta(provider, provider_results)
    return build_aggregated_weather_payload(
        location=location_payload,
        summary=summary,
        providers=provider_results,
        source=source,
    )


def get_enabled_providers(provider: str) -> list[str]:
    """根据 provider 参数返回需要查询的 provider 列表。"""

    if provider == "all":
        return PROVIDER_ORDER[:]
    if provider in PROVIDER_ORDER:
        return [provider]
    raise MCPError(
        MCPError.CONFIGURATION_ERROR,
        f"不支持的天气 provider: {provider}",
        {"provider": provider, "allowed": ["all", *PROVIDER_ORDER]},
    )


def query_providers_by_position(
    lat: float,
    lon: float,
    provider_names: list[str],
    location_name: str | None = None,
    timezone: str | None = None,
) -> dict:
    """按 provider 列表查询天气，并返回各 provider 的结果状态。"""

    results: dict[str, dict] = {}
    for provider_name in provider_names:
        try:
            results[provider_name] = _query_single_provider(
                provider_name,
                lat,
                lon,
                location_name=location_name,
                timezone=timezone,
            )
        except MCPError as exc:
            results[provider_name] = build_provider_error_payload(
                provider_name,
                exc.code,
                exc.message,
                exc.details,
            )
        except Exception as exc:
            results[provider_name] = build_provider_error_payload(
                provider_name,
                MCPError.EXTERNAL_API_ERROR,
                f"{provider_name} provider 查询失败: {exc}",
                {"lat": lat, "lon": lon},
            )
    return results


def _query_single_provider(
    provider_name: str,
    lat: float,
    lon: float,
    location_name: str | None = None,
    timezone: str | None = None,
) -> dict:
    """查询单个 provider 并返回标准化后的 provider 结果。"""

    if provider_name == "open-meteo":
        return open_meteo.get_weather_by_position(lat, lon, location_name=location_name, timezone=timezone)
    if provider_name == "qweather":
        return qweather.get_weather_by_position(lat, lon, location_name=location_name, timezone=timezone)
    if provider_name == "wttr":
        return wttr.get_weather_by_position(lat, lon, location_name=location_name, timezone=timezone)
    raise MCPError(
        MCPError.CONFIGURATION_ERROR,
        f"未知 provider: {provider_name}",
        {"provider": provider_name},
    )


def _build_summary(successful_provider_data: list[dict]) -> dict:
    """根据多个 provider 的标准化结果生成综合天气摘要。"""

    return {
        "current": _build_summary_current(successful_provider_data),
        "daily": _build_summary_daily(successful_provider_data),
        "hourly": _build_summary_hourly(successful_provider_data),
    }


def _build_summary_current(successful_provider_data: list[dict]) -> dict:
    """从多个成功 provider 中生成统一的当前天气摘要。"""

    primary_provider = _select_primary_provider_for_summary(successful_provider_data)
    primary_data = next(
        (item["data"]["current"] for item in successful_provider_data if item["provider"] == primary_provider),
        {},
    )
    merged = build_current_weather_payload(**primary_data)

    for field_name in merged:
        if merged[field_name] is not None:
            continue
        for item in successful_provider_data:
            value = item["data"].get("current", {}).get(field_name)
            if value is not None:
                merged[field_name] = value
                break
    return merged


def _build_summary_daily(successful_provider_data: list[dict]) -> list[dict]:
    """从多个成功 provider 中生成统一的日级天气预报摘要。"""

    for provider_name in PROVIDER_ORDER:
        for item in successful_provider_data:
            if item["provider"] == provider_name and item["data"].get("daily"):
                return item["data"]["daily"]
    return []


def _build_summary_hourly(successful_provider_data: list[dict]) -> list[dict]:
    """从多个成功 provider 中生成统一的小时级天气预报摘要。"""

    for provider_name in PROVIDER_ORDER:
        for item in successful_provider_data:
            if item["provider"] == provider_name and item["data"].get("hourly"):
                return item["data"]["hourly"]
    return []


def _select_primary_provider_for_summary(successful_provider_data: list[dict]) -> str | None:
    """选择用于生成摘要的主 provider。"""

    for provider_name in PROVIDER_ORDER:
        if any(item["provider"] == provider_name for item in successful_provider_data):
            return provider_name
    return None


def _build_source_meta(
    requested_provider: str,
    provider_results: dict,
) -> dict:
    """根据 provider 查询结果构造来源元信息。"""

    successful = [
        result["provider"]
        for result in provider_results.values()
        if result["status"] == "success"
    ]
    failed = [
        result["provider"]
        for result in provider_results.values()
        if result["status"] == "error"
    ]
    return {
        "query_mode": requested_provider,
        "successful_providers": successful,
        "failed_providers": failed,
        "summary_provider_policy": "open-meteo-first",
    }


def _ensure_any_provider_success(provider_results: dict) -> None:
    """确保至少有一个 provider 查询成功，否则抛出错误。"""

    if any(result["status"] == "success" for result in provider_results.values()):
        return

    errors = {
        provider_name: result["error"]
        for provider_name, result in provider_results.items()
        if result["status"] == "error"
    }
    raise MCPError(
        MCPError.EXTERNAL_API_ERROR,
        "所有天气 provider 查询均失败。",
        {"provider_errors": errors},
    )


def _build_location(
    lat: float,
    lon: float,
    location_name: str | None,
    timezone: str | None,
    successful_provider_data: list[dict],
) -> dict:
    """构造聚合结果的位置对象。"""

    resolved_name = location_name
    resolved_timezone = timezone
    for item in successful_provider_data:
        provider_location = item["data"].get("location", {})
        if resolved_name is None and provider_location.get("name") is not None:
            resolved_name = provider_location.get("name")
        if resolved_timezone is None and provider_location.get("timezone") is not None:
            resolved_timezone = provider_location.get("timezone")
    return build_location_payload(resolved_name, lat, lon, resolved_timezone)
