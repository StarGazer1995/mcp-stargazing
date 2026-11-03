"""Archive weather before its valid time and pair it with explicit independent observations."""

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from evaluations.forecast_verification import _number, _time, verify

CLOUD_DEFINITION = 'max_total_and_layers_percent'
PRECIPITATION_DEFINITION = 'preceding_hour_total_precipitation_gt_0.1mm'
CLOUD_FIELDS = (
    'cloud_cover_percent',
    'cloud_cover_low_percent',
    'cloud_cover_mid_percent',
    'cloud_cover_high_percent',
)


def _valid_time(value, timezone):
    stamp = datetime.fromisoformat(value)
    if stamp.utcoffset() is None:
        zone = ZoneInfo(timezone)
        if (
            stamp.replace(tzinfo=zone, fold=0).utcoffset()
            != stamp.replace(tzinfo=zone, fold=1).utcoffset()
        ):
            raise ValueError('Ambiguous or nonexistent local forecast time')
        stamp = stamp.replace(tzinfo=zone)
    return stamp.astimezone(UTC)


def make_snapshot(site_id, weather, started_at, completed_at):
    """Preserve provider results without relabeling retrieval as model issue time."""
    start, end = _time(started_at), _time(completed_at)
    if not isinstance(site_id, str) or not site_id.strip() or end < start:
        raise ValueError('A site identity and ordered retrieval timestamps are required')
    return {
        'format_version': 1,
        'site_id': site_id,
        'retrieval_started_at': start.isoformat(),
        'retrieval_completed_at': end.isoformat(),
        'weather': weather,
    }


def write_snapshot(snapshot, out_dir):
    """Every capture has its own file; repeated runs cannot overwrite an earlier forecast."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f'forecast-{uuid4().hex}.json'
    with path.open('x') as stream:
        json.dump(snapshot, stream, ensure_ascii=False, indent=2, allow_nan=False)
    return path


def pair_snapshots(snapshots, observations):
    """Exact site/time joins only, with explicit cloud definitions and duplicate rejection.

    Forecast lead time is measured from completed retrieval, a conservative availability
    bound. The weather API does not expose model issue time. Each distinct retrieval is
    a separate forecast sample; repeating the same archive file does not multiply it.
    """
    index, ambiguous, rejected = {}, set(), []
    for position, observation in enumerate(observations):
        try:
            key = (observation['site_id'], _time(observation['valid_time']).astimezone(UTC))
            if not key[0] or not observation['source'] or observation['kind'] != 'observation':
                raise ValueError('An explicit observation identity and source are required')
            if key in index:
                ambiguous.add(key)
                raise ValueError('Duplicate observation site/time; no reference selected')
            index[key] = observation
        except (KeyError, TypeError, ValueError) as exc:
            rejected.append({'observation': position, 'reason': str(exc)})

    pairs, seen, unmatched, nonfuture = [], set(), 0, 0
    for position, snapshot in enumerate(snapshots):
        try:
            if snapshot['format_version'] != 1:
                raise ValueError('Unsupported forecast archive format')
            available = _time(snapshot['retrieval_completed_at']).astimezone(UTC)
            if available < _time(snapshot['retrieval_started_at']):
                raise ValueError('Retrieval completed before it started')
            weather, site_id = snapshot['weather'], snapshot['site_id']
            for name, provider in weather['providers'].items():
                if provider.get('status') != 'success':
                    continue
                data = provider['data']
                timezone = data['location'].get('timezone') or weather['location']['timezone']
                times = set()
                for hour in data.get('hourly', []):
                    valid = _valid_time(hour['time'], timezone)
                    if valid in times:
                        raise ValueError('Duplicate forecast valid time')
                    times.add(valid)
                for hour in data.get('hourly', []):
                    valid = _valid_time(hour['time'], timezone)
                    identity = (site_id, name, available, valid)
                    if identity in seen:
                        continue
                    seen.add(identity)
                    if valid <= available:
                        nonfuture += 1
                        continue
                    key = (site_id, valid)
                    if key not in index or key in ambiguous:
                        unmatched += 1
                        continue
                    observation = index[key]
                    if any(
                        observation.get(field) != weather['location'][field]
                        for field in ('lat', 'lon')
                    ):
                        raise ValueError('Observation coordinates must match the forecast query')
                    if observation['source'] == name:
                        raise ValueError('Forecast provider cannot serve as its own observation')
                    clouds = [_number(hour.get(field), 100) for field in CLOUD_FIELDS]
                    known = [value for value in clouds if value is not None]
                    cloud = max(known) if known else None
                    # Different cloud measurement definitions cannot earn a cloud accuracy result.
                    if observation.get('cloud_definition') != CLOUD_DEFINITION:
                        cloud = None
                    # Open-Meteo defines >0.1 mm during the preceding hour. Neither
                    # a point-in-time rain label nor another provider proves that event.
                    rain_start = valid - timedelta(hours=1)
                    probability = None
                    if (
                        name == 'open-meteo'
                        and observation.get('precipitation_definition') == PRECIPITATION_DEFINITION
                        and rain_start >= available
                    ):
                        probability = _number(hour.get('precipitation_probability'), 1)
                    forecast = {
                        'source': name,
                        'issued_at': None,
                        'available_at': available.isoformat(),
                        'retrieved_at': snapshot['retrieval_started_at'],
                        'cloud_definition': CLOUD_DEFINITION,
                        'effective_cloud_percent': cloud,
                        'precipitation_probability': probability,
                        'precipitation_definition': PRECIPITATION_DEFINITION
                        if name == 'open-meteo'
                        else None,
                        'precipitation_interval_start': rain_start.isoformat()
                        if name == 'open-meteo'
                        else None,
                        'precipitation_interval_end': valid.isoformat()
                        if name == 'open-meteo'
                        else None,
                    }
                    pair = {
                        'site_id': site_id,
                        'valid_time': valid.isoformat(),
                        'forecast': forecast,
                        'observation': observation,
                    }
                    if not verify([pair])['matched_pairs']:
                        rejected.append({'archive': position, 'reason': 'No comparable fields'})
                    else:
                        pairs.append(pair)
        except (KeyError, TypeError, ValueError) as exc:
            rejected.append({'archive': position, 'reason': str(exc)})
    return {
        'pairs': pairs,
        'unmatched_forecast_hours': unmatched,
        'excluded_nonfuture_hours': nonfuture,
        'rejected': rejected,
        'verification': verify(pairs),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest='action', required=True)
    capture = actions.add_parser('capture', help='Fetch and archive one explicit site')
    capture.add_argument('--site-id', required=True)
    capture.add_argument('--lat', type=float, required=True)
    capture.add_argument('--lon', type=float, required=True)
    capture.add_argument('--timezone', required=True)
    capture.add_argument(
        '--provider', choices=['open-meteo', 'qweather', 'wttr'], default='open-meteo'
    )
    capture.add_argument('--out-dir', type=Path, required=True)
    pair = actions.add_parser('pair', help='Join archives to independent observations')
    pair.add_argument('--archives', type=Path, nargs='+', required=True)
    pair.add_argument('--observations', type=Path, required=True)
    pair.add_argument('--out-dir', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.action == 'capture':
        from src.functions.weather.service import get_aggregated_weather_by_position
        from src.utils import validate_coordinates

        if not validate_coordinates(args.lat, args.lon):
            parser.error('Invalid coordinates')
        ZoneInfo(args.timezone)
        start = datetime.now(UTC).isoformat()
        weather = get_aggregated_weather_by_position(
            args.lat, args.lon, provider=args.provider, timezone=args.timezone
        )
        snapshot = make_snapshot(
            args.site_id, weather.model_dump(mode='json'), start, datetime.now(UTC).isoformat()
        )
        print(write_snapshot(snapshot, args.out_dir))
        return 0
    snapshots = [json.loads(path.read_text()) for path in args.archives]
    observations = json.loads(args.observations.read_text())
    if not isinstance(observations, list):
        parser.error('Observations must be a JSON array')
    result = pair_snapshots(snapshots, observations)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / 'forecast-pairs.json').write_text(json.dumps(result['pairs'], indent=2))
    (args.out_dir / 'forecast-pairing.json').write_text(json.dumps(result, indent=2))
    print(json.dumps({key: value for key, value in result.items() if key != 'pairs'}))
    return 0 if result['pairs'] and not result['rejected'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
