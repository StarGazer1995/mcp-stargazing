"""Aggregation service for multi-provider weather queries.

Internally uses Pydantic models for type-safe data handling.
Public API functions return AggregatedWeatherResponse (a Pydantic model).
"""

from concurrent.futures import ThreadPoolExecutor, as_completed

from src.functions.weather.geocoding import resolve_place_name
from src.functions.weather.providers import open_meteo, qweather, wttr
from src.response import MCPError
from src.schemas import ProviderType
from src.schemas.weather import (
    AggregatedWeatherResponse,
    LocationInfo,
    ProviderError,
    ProviderErrorDetail,
    ProviderSuccess,
    SourceMeta,
    WeatherSummary,
)

PROVIDER_ORDER = ['open-meteo', 'qweather', 'wttr']


def get_aggregated_weather_by_name(
    place_name: str,
    provider: str = 'all',
) -> AggregatedWeatherResponse:
    """根据地点名称查询并聚合多个天气提供商的结果。"""

    location = resolve_place_name(place_name)
    return get_aggregated_weather_by_position(
        location.lat,
        location.lon,
        provider=provider,
        location_name=location.name,
        timezone=location.timezone,
    )


def _query_provider_safe(
    provider_name: str,
    lat: float,
    lon: float,
    location_name: str | None = None,
    timezone: str | None = None,
) -> tuple[str, ProviderSuccess | ProviderError]:
    """Query a single provider, always returning (provider_name, result_or_error)."""
    try:
        return provider_name, _query_single_provider(
            provider_name,
            lat,
            lon,
            location_name=location_name,
            timezone=timezone,
        )
    except MCPError as exc:
        return provider_name, ProviderError(
            provider=provider_name,
            error=ProviderErrorDetail(code=exc.code, message=exc.message, details=exc.details),
        )
    except Exception as exc:
        return provider_name, ProviderError(
            provider=provider_name,
            error=ProviderErrorDetail(
                code=MCPError.EXTERNAL_API_ERROR,
                message=f'{provider_name} provider 查询失败: {exc}',
                details={'lat': lat, 'lon': lon},
            ),
        )


def get_aggregated_weather_by_position(
    lat: float,
    lon: float,
    provider: str = 'all',
    location_name: str | None = None,
    timezone: str | None = None,
) -> AggregatedWeatherResponse:
    """根据经纬度查询并聚合多个天气提供商的结果。"""

    provider_type = ProviderType.from_str(provider)
    provider_names = _get_enabled_providers(provider_type)

    provider_results: dict[str, ProviderSuccess | ProviderError] = {}
    with ThreadPoolExecutor(max_workers=len(provider_names)) as executor:
        futures = [
            executor.submit(
                _query_provider_safe,
                pname,
                lat,
                lon,
                location_name=location_name,
                timezone=timezone,
            )
            for pname in provider_names
        ]
        for future in as_completed(futures):
            name, result = future.result()
            provider_results[name] = result

    _ensure_any_provider_success(provider_results)

    successful_providers = [r for r in provider_results.values() if isinstance(r, ProviderSuccess)]

    location = _build_location(lat, lon, location_name, timezone, successful_providers)
    summary = _build_summary(successful_providers)
    source = _build_source_meta(provider, provider_results)

    return AggregatedWeatherResponse(
        location=location,
        summary=summary,
        providers=provider_results,
        source=source,
    )


def _get_enabled_providers(provider_type: ProviderType) -> list[str]:
    """根据 provider 类型返回需要查询的 provider 列表。"""

    if provider_type == ProviderType.ALL:
        return PROVIDER_ORDER[:]
    if provider_type.value in PROVIDER_ORDER:
        return [provider_type.value]
    raise MCPError(
        MCPError.CONFIGURATION_ERROR,
        f'不支持的天气 provider: {provider_type.value}',
        {'provider': provider_type.value, 'allowed': ['all', *PROVIDER_ORDER]},
    )


def _query_single_provider(
    provider_name: str,
    lat: float,
    lon: float,
    location_name: str | None = None,
    timezone: str | None = None,
) -> ProviderSuccess:
    """查询单个 provider 并返回 ProviderSuccess 模型。"""

    if provider_name == 'open-meteo':
        return open_meteo.get_weather_by_position(
            lat, lon, location_name=location_name, timezone=timezone
        )
    if provider_name == 'qweather':
        return qweather.get_weather_by_position(
            lat, lon, location_name=location_name, timezone=timezone
        )
    if provider_name == 'wttr':
        return wttr.get_weather_by_position(
            lat, lon, location_name=location_name, timezone=timezone
        )
    raise MCPError(
        MCPError.CONFIGURATION_ERROR,
        f'未知 provider: {provider_name}',
        {'provider': provider_name},
    )


def _build_summary(successful_providers: list[ProviderSuccess]) -> WeatherSummary:
    """根据多个成功 provider 的标准化结果生成综合天气摘要。"""

    return WeatherSummary(
        current=_build_summary_current(successful_providers),
        daily=_build_summary_daily(successful_providers),
        hourly=_build_summary_hourly(successful_providers),
    )


def _build_summary_current(successful_providers: list[ProviderSuccess]) -> dict:
    """从多个成功 provider 中生成统一的当前天气摘要。

    Uses the preferred provider's data, falling back to others for None fields.
    """

    primary_provider = _select_primary_provider(successful_providers)
    if primary_provider is None:
        return {}

    primary = primary_provider.data.current
    merged = primary.model_dump()

    for field_name in merged:
        if merged[field_name] is not None:
            continue
        for p in successful_providers:
            value = getattr(p.data.current, field_name, None)
            if value is not None:
                merged[field_name] = value
                break
    return merged


def _build_summary_daily(successful_providers: list[ProviderSuccess]) -> list[dict]:
    """从多个成功 provider 中生成统一的日级天气预报摘要。"""

    for provider_name in PROVIDER_ORDER:
        for p in successful_providers:
            if p.provider == provider_name and p.data.daily:
                return [d.model_dump() for d in p.data.daily]
    return []


def _build_summary_hourly(successful_providers: list[ProviderSuccess]) -> list[dict]:
    """从多个成功 provider 中生成统一的小时级天气预报摘要。"""

    for provider_name in PROVIDER_ORDER:
        for p in successful_providers:
            if p.provider == provider_name and p.data.hourly:
                return [h.model_dump() for h in p.data.hourly]
    return []


def _select_primary_provider(successful_providers: list[ProviderSuccess]) -> ProviderSuccess | None:
    """选择用于生成摘要的首选 provider（按 PROVIDER_ORDER 优先级）。"""

    for provider_name in PROVIDER_ORDER:
        for p in successful_providers:
            if p.provider == provider_name:
                return p
    return None


def _build_source_meta(
    requested_provider: str,
    provider_results: dict[str, ProviderSuccess | ProviderError],
) -> SourceMeta:
    """根据 provider 查询结果构造来源元信息。"""

    successful = sorted(
        r.provider for r in provider_results.values() if isinstance(r, ProviderSuccess)
    )
    failed = sorted(r.provider for r in provider_results.values() if isinstance(r, ProviderError))
    return SourceMeta(
        query_mode=requested_provider,
        successful_providers=successful,
        failed_providers=failed,
        summary_provider_policy='open-meteo-first',
    )


def _ensure_any_provider_success(
    provider_results: dict[str, ProviderSuccess | ProviderError],
) -> None:
    """确保至少有一个 provider 查询成功，否则抛出错误。"""

    if any(isinstance(r, ProviderSuccess) for r in provider_results.values()):
        return

    errors = {
        name: r.error.model_dump() if isinstance(r, ProviderError) else {}
        for name, r in provider_results.items()
    }
    raise MCPError(
        MCPError.EXTERNAL_API_ERROR,
        '所有天气 provider 查询均失败。',
        {'provider_errors': errors},
    )


def _build_location(
    lat: float,
    lon: float,
    location_name: str | None,
    timezone: str | None,
    successful_providers: list[ProviderSuccess],
) -> LocationInfo:
    """构造聚合结果的位置对象。"""

    resolved_name = location_name
    resolved_timezone = timezone
    for p in successful_providers:
        loc = p.data.location
        if resolved_name is None and loc.name is not None:
            resolved_name = loc.name
        if resolved_timezone is None and loc.timezone is not None:
            resolved_timezone = loc.timezone
    return LocationInfo(name=resolved_name, lat=lat, lon=lon, timezone=resolved_timezone)
