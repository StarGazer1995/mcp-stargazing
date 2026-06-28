"""Aggregation service for multi-provider weather queries.

Internally uses Pydantic models for type-safe data handling.
Public API functions return AggregatedWeatherResponse (a Pydantic model).
"""

from src.functions.weather.common import WeatherProvider
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

PROVIDER_ORDER = [open_meteo.PROVIDER_NAME, qweather.PROVIDER_NAME, wttr.PROVIDER_NAME]

_PROVIDER_MODULES: dict[str, WeatherProvider] = {
    open_meteo.PROVIDER_NAME: open_meteo,
    qweather.PROVIDER_NAME: qweather,
    wttr.PROVIDER_NAME: wttr,
}


def get_aggregated_weather_by_name(
    place_name: str,
    provider: str = 'all',
) -> AggregatedWeatherResponse:
    """根据地点名称查询并聚合多个天气提供商的结果。

    每个 provider 内部自行处理地名→坐标的转换，无需统一 geocoding 层。
    """

    provider_type = ProviderType.from_str(provider)
    provider_names = _get_enabled_providers(provider_type)

    return _aggregate_weather(
        provider=provider,
        provider_names=provider_names,
        query_fn=lambda pname: _query_single_provider_by_name(pname, place_name),
        build_location_fn=lambda sp: _build_location_from_providers(sp, place_name),
        error_label='(by_name) ',
        error_context={'place_name': place_name},
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

    return _aggregate_weather(
        provider=provider,
        provider_names=provider_names,
        query_fn=lambda pname: _query_single_provider(
            pname, lat, lon, location_name=location_name, timezone=timezone
        ),
        build_location_fn=lambda sp: _build_location(lat, lon, location_name, timezone, sp),
        error_label='',
        error_context={'lat': lat, 'lon': lon},
    )


def _aggregate_weather(
    provider: str,
    provider_names: list[str],
    query_fn,
    build_location_fn,
    error_label: str,
    error_context: dict,
) -> AggregatedWeatherResponse:
    """Generic provider-iteration + aggregation template.

    Both by_name and by_position paths share the same loop → result →
    build-location → summary flow.  Only the per-provider query function
    and the location-construction logic differ.
    """

    provider_results: dict[str, ProviderSuccess | ProviderError] = {}
    for pname in provider_names:
        try:
            provider_results[pname] = query_fn(pname)
        except MCPError as exc:
            provider_results[pname] = ProviderError(
                provider=pname,
                error=ProviderErrorDetail(code=exc.code, message=exc.message, details=exc.details),
            )
        except Exception as exc:
            provider_results[pname] = ProviderError(
                provider=pname,
                error=ProviderErrorDetail(
                    code=MCPError.EXTERNAL_API_ERROR,
                    message=f'{pname} provider {error_label}查询失败: {exc}',
                    details=error_context,
                ),
            )

    _ensure_any_provider_success(provider_results)

    successful_providers = [r for r in provider_results.values() if isinstance(r, ProviderSuccess)]

    location = build_location_fn(successful_providers)
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


def _get_provider_module(provider_name: str):
    """根据名称获取 provider 模块，未知时抛出 MCPError。"""

    mod = _PROVIDER_MODULES.get(provider_name)
    if mod is None:
        raise MCPError(
            MCPError.CONFIGURATION_ERROR,
            f'未知 provider: {provider_name}',
            {'provider': provider_name},
        )
    return mod


def _query_single_provider(
    provider_name: str,
    lat: float,
    lon: float,
    location_name: str | None = None,
    timezone: str | None = None,
) -> ProviderSuccess:
    """查询单个 provider（按坐标）并返回 ProviderSuccess 模型。"""

    return _get_provider_module(provider_name).get_weather_by_position(
        lat, lon, location_name=location_name, timezone=timezone
    )


def _query_single_provider_by_name(
    provider_name: str,
    place_name: str,
) -> ProviderSuccess:
    """查询单个 provider（按地名）并返回 ProviderSuccess 模型。"""

    return _get_provider_module(provider_name).get_weather_by_name(place_name)


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

    successful = [r.provider for r in provider_results.values() if isinstance(r, ProviderSuccess)]
    failed = [r.provider for r in provider_results.values() if isinstance(r, ProviderError)]
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
    """构造聚合结果的位置对象（按坐标查询时使用）。"""

    resolved_name = location_name
    resolved_timezone = timezone
    for p in successful_providers:
        loc = p.data.location
        if resolved_name is None and loc.name is not None:
            resolved_name = loc.name
        if resolved_timezone is None and loc.timezone is not None:
            resolved_timezone = loc.timezone
    return LocationInfo(name=resolved_name, lat=lat, lon=lon, timezone=resolved_timezone)


def _build_location_from_providers(
    successful_providers: list[ProviderSuccess],
    fallback_name: str,
) -> LocationInfo:
    """从成功 provider 的返回数据中提取位置信息（按地名查询时使用）。

    坐标取自第一个成功 provider，name/timezone 通过 _build_location 统一补充。
    """

    primary = successful_providers[0].data.location
    return _build_location(
        lat=primary.lat,
        lon=primary.lon,
        location_name=primary.name or fallback_name,
        timezone=primary.timezone,
        successful_providers=successful_providers,
    )
