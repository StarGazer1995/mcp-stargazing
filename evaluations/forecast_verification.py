"""Score archived forecasts against explicit, time-matched observations."""

import argparse
import json
import math
from datetime import datetime
from pathlib import Path


def _time(value):
    result = datetime.fromisoformat(value)
    if result.utcoffset() is None:
        raise ValueError('Timestamps must carry a timezone')
    return result


def _number(value, maximum):
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        return None
    return float(value) if math.isfinite(value) and 0 <= value <= maximum else None


def verify(pairs):
    clouds, rain, rejected, lead_hours = [], [], [], []
    for index, pair in enumerate(pairs):
        try:
            forecast = pair['forecast']
            observation = pair['observation']
            if not pair['site_id'] or pair['site_id'] != observation['site_id']:
                raise ValueError('Site identities must match')
            if not observation['source'] or not forecast['source']:
                raise ValueError('Both sources are required')
            # Never compare an old forecast to a later forecast as ground truth.
            if observation.get('kind') != 'observation':
                raise ValueError('Reference must be explicitly labelled observation')
            valid = _time(pair['valid_time'])
            if valid != _time(observation['valid_time']):
                raise ValueError('Valid times must match')
            lead = (valid - _time(forecast['issued_at'])).total_seconds() / 3600
            if lead < 0:
                raise ValueError('Forecast was issued after the event')
            f = _number(forecast.get('effective_cloud_percent'), 100)
            o = _number(observation.get('effective_cloud_percent'), 100)
            probability = _number(forecast.get('precipitation_probability'), 1)
            occurred = observation.get('precipitation_occurred')
            if f is None and probability is None:
                raise ValueError('No valid forecast field')
            if (f is None or o is None) and (probability is None or not isinstance(occurred, bool)):
                raise ValueError('No paired valid observation field')
            if f is not None and o is not None:
                clouds.append(abs(f - o))
            if probability is not None and isinstance(occurred, bool):
                rain.append((probability - int(occurred)) ** 2)
            lead_hours.append(lead)
        except (KeyError, ValueError, TypeError) as exc:
            rejected.append({'index': index, 'reason': str(exc)})
    return {
        'input_pairs': len(pairs),
        'matched_pairs': len(lead_hours),
        'rejected': rejected,
        'cloud_pairs': len(clouds),
        'cloud_mae_percentage_points': sum(clouds) / len(clouds) if clouds else None,
        'rain_pairs': len(rain),
        'rain_brier_score': sum(rain) / len(rain) if rain else None,
        'lead_hours': lead_hours,
        'scope': 'Supplied matched observations only; not a general forecast skill claim.',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pairs', type=Path, required=True)
    parser.add_argument('--out-dir', type=Path, required=True)
    args = parser.parse_args()
    pairs = json.loads(args.pairs.read_text())
    if not isinstance(pairs, list):
        parser.error('pairs must be a JSON array')
    result = verify(pairs)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / 'forecast-verification.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result))
    return 0 if result['matched_pairs'] and not result['rejected'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
