"""Air-composition enrichment inside weather aggregation, with exact valid-time joins."""

import math
import time
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from src.functions.weather.providers._http import fetch_weather_json
from src.response import MCPError
from src.schemas.atmosphere import AtmosphericSource, AtmosphericState
from src.schemas.weather import NormalizedWeatherData

WEATHER_SOURCE = 'open-meteo-weather'
AIR_SOURCE = 'open-meteo-cams-global'
AIR_URL = 'https://air-quality-api.open-meteo.com/v1/air-quality'
WEATHER_FIELDS = {
    'boundary_layer_height_m': ('boundary_layer_height', 'm'),
    'visibility_km': ('visibility', 'm'),
}
AIR_FIELDS = {
    'pm2_5_ug_m3': ('pm2_5', 'μg/m³'),
    'pm10_ug_m3': ('pm10', 'μg/m³'),
    'no2_ug_m3': ('nitrogen_dioxide', 'μg/m³'),
    'o3_ug_m3': ('ozone', 'μg/m³'),
    'so2_ug_m3': ('sulphur_dioxide', 'μg/m³'),
    'co_ug_m3': ('carbon_monoxide', 'μg/m³'),
    'aod_550nm': ('aerosol_optical_depth', ''),
    'dust_ug_m3': ('dust', 'μg/m³'),
}
INTERPRETATION_LIMITS = (
    'All atmospheric values are model estimates, including past/current hours. '
    'Forecasts are not observations; retrieval time is not model run time. '
    'AOD is column extinction, not surface PM, horizontal visibility or astronomical seeing. '
    'Boundary-layer height is above local model ground, not a pollution ceiling. '
    'Wind and pollutant trends do not establish source cities or traffic contributions. '
    'No AQI, health category or observing score is inferred.'
)


def utc_now() -> datetime:
    return datetime.now(UTC)


def fetch_air_quality(lat: float, lon: float) -> dict:
    """Fetch the air horizon once; the existing weather request is reused for dispersion."""
    for attempt in range(3):
        try:
            return fetch_weather_json(
                AIR_URL,
                service_name='Open-Meteo air quality',
                context={'lat': lat, 'lon': lon},
                params={
                    'latitude': lat,
                    'longitude': lon,
                    'timezone': 'UTC',
                    'timeformat': 'unixtime',
                    'forecast_days': 5,
                    'domains': 'cams_global',
                    'hourly': ','.join(variable for variable, _ in AIR_FIELDS.values()),
                },
                timeout_s=5.0,
                rate_limit_message='Air-quality provider rate limited; retry later.',
            )
        except MCPError as exc:
            if attempt == 2 or exc.code not in {
                MCPError.API_TIMEOUT,
                MCPError.NETWORK_ERROR,
                MCPError.API_RATE_LIMIT,
            }:
                raise
            time.sleep(2**attempt)


def _number(value, *, nonnegative: bool = True) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return float(value) if math.isfinite(value) and (not nonnegative or value >= 0) else None
    except OverflowError:
        return None


def _timestamp(value, timezone: str) -> int | None:
    """Do not guess ambiguous/nonexistent local times during DST transitions."""
    try:
        if isinstance(value, str):
            dt = datetime.fromisoformat(value)
            if dt.tzinfo is None:
                tz = ZoneInfo(timezone)
                if (
                    dt.replace(tzinfo=tz, fold=0).utcoffset()
                    != dt.replace(tzinfo=tz, fold=1).utcoffset()
                ):
                    return None
                dt = dt.replace(tzinfo=tz)
            return int(dt.timestamp())
        if _number(value) is not None:
            return int(datetime.fromtimestamp(value, UTC).timestamp())
    except (ValueError, TypeError, OverflowError, OSError, KeyError):
        pass
    return None


def _series(raw: dict, fields: dict, *, unix: bool) -> tuple[dict, bool]:
    hourly, units = raw['hourly'], raw['hourly_units']
    times = hourly['time']
    if not isinstance(times, list) or (unix and units.get('time') != 'unixtime'):
        raise ValueError('Invalid atmospheric time column')
    result = {}
    partial = False
    for index, value in enumerate(times):
        stamp = _timestamp(value, raw.get('timezone') or 'UTC')
        if stamp is None:
            partial = True
            continue
        if stamp in result:
            raise ValueError('Duplicate atmospheric valid time')
        values = {}
        for name, (variable, unit) in fields.items():
            column = hourly.get(variable)
            actual_unit = units.get(variable)
            if isinstance(actual_unit, str):
                actual_unit = actual_unit.replace('µ', 'μ')
            number = (
                _number(column[index])
                if (isinstance(column, list) and len(column) == len(times) and actual_unit == unit)
                else None
            )
            if number is not None and name == 'visibility_km':
                number /= 1000
            values[name] = number
            partial |= number is None
        result[stamp] = values
    if not any(value is not None for row in result.values() for value in row.values()):
        raise ValueError('No usable atmospheric data')
    return result, partial


def _source(raw: dict, fields: dict, now: datetime, *, air: bool, error: dict | None = None):
    source = AtmosphericSource(
        status='error',
        dataset='CAMS global atmospheric composition forecast' if air else 'Best-match weather',
        retrieved_at=now.isoformat(),
        documentation_url='https://open-meteo.com/en/docs/air-quality-api'
        if air
        else 'https://open-meteo.com/en/docs',
        attribution='CAMS / Copernicus Atmosphere Monitoring Service via Open-Meteo'
        if air
        else 'Open-Meteo and its best-match weather providers',
        spatial_resolution='approximately 45 km native global grid' if air else 'model-dependent',
        native_time_resolution='3 hours; hourly output may be interpolated'
        if air
        else 'model-dependent; requested output is hourly',
        units={
            name: 'km' if name == 'visibility_km' else unit for name, (_, unit) in fields.items()
        },
        warnings=[INTERPRETATION_LIMITS],
    )
    try:
        if error is not None:
            raise MCPError(error['code'], error['message'])
        rows, partial = _series(raw, fields, unix=air)
        source.coverage_start_time = datetime.fromtimestamp(min(rows), UTC).isoformat()
        source.coverage_end_time = datetime.fromtimestamp(max(rows), UTC).isoformat()
        source.grid_lat = _number(raw.get('latitude'), nonnegative=False)
        source.grid_lon = _number(raw.get('longitude'), nonnegative=False)
        source.grid_elevation_m = _number(raw.get('elevation'), nonnegative=False)
        source.status = 'partial' if partial else 'success'
        if partial:
            source.warnings.append(
                'Missing, invalid or unit-mismatched values remain null/unknown.'
            )
        return rows, source
    except (MCPError, ValueError, KeyError, TypeError, AttributeError) as exc:
        source.error_code = exc.code if isinstance(exc, MCPError) else MCPError.EXTERNAL_API_ERROR
        source.error_message = (
            str(exc) if isinstance(exc, MCPError) else 'Invalid atmospheric payload.'
        )
        return {}, source


def enrich_weather(data: NormalizedWeatherData, raw: dict, now: datetime) -> NormalizedWeatherData:
    """Attach optional states, without extending either provider's valid horizon."""
    weather, weather_source = _source(raw, WEATHER_FIELDS, now, air=False)
    air, air_source = _source(
        raw.get('_air_quality', {}), AIR_FIELDS, now, air=True, error=raw.get('_air_quality_error')
    )
    data.atmosphere_sources = {WEATHER_SOURCE: weather_source, AIR_SOURCE: air_source}
    tz = data.location.timezone or 'UTC'
    current_hour = now.replace(minute=0, second=0, microsecond=0)

    def state(stamp: int | None) -> AtmosphericState | None:
        if stamp is None:
            return None
        values = weather.get(stamp, {}) | air.get(stamp, {})
        sources = {
            key: WEATHER_SOURCE if key in WEATHER_FIELDS else AIR_SOURCE
            for key, value in values.items()
            if value is not None
        }
        if not sources:
            return None
        dt = datetime.fromtimestamp(stamp, UTC)
        return AtmosphericState(
            time=dt.isoformat(),
            temporal_role='forecast'
            if dt > current_hour
            else ('current_model_estimate' if dt == current_hour else 'past_model_estimate'),
            field_sources=sources,
            **values,
        )

    for item in data.hourly:
        item.atmosphere = state(_timestamp(item.time, tz))
    stamp = _timestamp(data.current.observation_time, tz)
    data.current.atmosphere = state(stamp - stamp % 3600) if stamp is not None else None
    return data
