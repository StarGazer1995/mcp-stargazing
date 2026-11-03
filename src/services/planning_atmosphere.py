"""Describe atmospheric model evidence inside a selected window, without scoring it."""

import math
from datetime import UTC, datetime

from src.schemas.atmosphere import AtmosphericSource
from src.schemas.planning import ObservationWindow

FIELD_UNITS = {
    'boundary_layer_height_m': 'm',
    'visibility_km': 'km',
    'pm2_5_ug_m3': 'μg/m³',
    'pm10_ug_m3': 'μg/m³',
    'no2_ug_m3': 'μg/m³',
    'o3_ug_m3': 'μg/m³',
    'so2_ug_m3': 'μg/m³',
    'co_ug_m3': 'μg/m³',
    'aod_550nm': '',
    'dust_ug_m3': 'μg/m³',
}


def _instant(value):
    try:
        stamp = datetime.fromisoformat(value)
        return stamp.astimezone(UTC) if stamp.utcoffset() is not None else None
    except (TypeError, ValueError, OverflowError):
        return None


def _nonnegative(value):
    try:
        if not isinstance(value, bool) and isinstance(value, (int, float)):
            return float(value) if math.isfinite(value) and value >= 0 else None
    except OverflowError:
        pass
    return None


def summarize_window_atmosphere(
    hourly: list[dict],
    sources: dict,
    window: ObservationWindow,
) -> dict:
    """Use exact hourly valid times, per-field units and source horizons; never interpolate.

    Counts describe valid-time samples, not measured durations. The last hourly sample
    may precede a clipped window end by less than one hour. Means are unweighted model
    sample means, not exposure-integrated transparency or calibrated observing quality.
    """
    start, end = _instant(window.start_time), _instant(window.end_time)
    if start is None or end is None or end <= start:
        raise ValueError('A selected window with ordered offset-aware bounds is required')
    expected = math.ceil((end - start).total_seconds() / 3600)
    validated, invalid_sources = {}, []
    if not isinstance(sources, dict):
        sources = {}
        invalid_sources.append('atmosphere_sources')
    for key, raw in sources.items():
        try:
            source = AtmosphericSource.model_validate(raw)
            if _instant(source.retrieved_at) is None:
                raise ValueError('Atmospheric retrieval time must carry an offset')
            validated[key] = source
        except ValueError:
            invalid_sources.append(key)

    records, duplicates = {}, set()
    for item in hourly:
        stamp = _instant(item.get('time'))
        if stamp is None or not start <= stamp < end or (stamp - start).total_seconds() % 3600 != 0:
            continue
        if stamp in records:
            duplicates.add(stamp)
        records[stamp] = item

    values = {key: [] for key in FIELD_UNITS}
    field_sources = {key: set() for key in FIELD_UNITS}
    roles = set()
    for stamp, item in records.items():
        state = item.get('atmosphere')
        if (
            stamp in duplicates
            or not isinstance(state, dict)
            or _instant(state.get('time')) != stamp
            or state.get('data_kind') != 'model_estimate'
            or not isinstance(state.get('temporal_role'), str)
            or state.get('temporal_role')
            not in {'forecast', 'current_model_estimate', 'past_model_estimate'}
            or not isinstance(state.get('field_sources'), dict)
        ):
            continue
        for key, unit in FIELD_UNITS.items():
            value = _nonnegative(state.get(key))
            source_key = state['field_sources'].get(key)
            source = validated.get(source_key) if isinstance(source_key, str) else None
            if value is None or source is None or source.status == 'error':
                continue
            lower = _instant(source.coverage_start_time)
            upper = _instant(source.coverage_end_time)
            if (
                source.units.get(key) != unit
                or lower is None
                or upper is None
                or not lower <= stamp <= upper
            ):
                continue
            values[key].append(value)
            field_sources[key].add(source_key)
            roles.add(state['temporal_role'])

    fields = {}
    for key, unit in FIELD_UNITS.items():
        known = values[key]
        scale = max(known, default=0.0)
        fields[key] = {
            'unit': unit,
            'valid_samples': len(known),
            'missing_samples': expected - len(known),
            'minimum': min(known) if known else None,
            'maximum': scale if known else None,
            'mean': (
                scale * (math.fsum(value / scale for value in known) / len(known))
                if scale
                else 0.0
                if known
                else None
            ),
            'sources': sorted(field_sources[key]),
        }
    counts = [len(known) for known in values.values()]
    return {
        'status': 'available'
        if all(count == expected for count in counts)
        else 'partial'
        if any(counts)
        else 'unknown',
        'data_kind': 'model_estimate',
        'interval_start': window.start_time,
        'interval_end': window.end_time,
        'sampling': 'exact_hourly_valid_times_no_interpolation',
        'expected_samples': expected,
        'aggregation': 'unweighted_valid_sample_mean_and_range',
        'fields': fields,
        'sources': {key: source.model_dump(mode='json') for key, source in validated.items()},
        'invalid_sources': sorted(invalid_sources),
        'temporal_roles': sorted(roles),
        'affects_ranking': False,
        'interpretation': (
            'Atmospheric model ranges describe the selected window only. Missing fields remain '
            'unknown; partial means do not fill gaps. AOD is column extinction, not seeing or '
            'a calibrated transparency score. Boundary-layer height is not a pollution ceiling. '
            'These fields establish no pollution-source attribution and do not change ranking, '
            'window selection or observing eligibility.'
        ),
    }
