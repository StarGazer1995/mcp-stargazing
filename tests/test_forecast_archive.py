"""Forecast evidence cannot be fabricated by late capture, repeated inputs or mismatched truth."""

import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from evaluations.forecast_archive import (
    CLOUD_DEFINITION,
    PRECIPITATION_DEFINITION,
    main,
    make_snapshot,
    pair_snapshots,
    write_snapshot,
)


@pytest.fixture
def snapshot():
    return make_snapshot(
        'test-site',
        {
            'location': {'lat': 30, 'lon': 120, 'timezone': 'Asia/Shanghai'},
            'providers': {
                'open-meteo': {
                    'status': 'success',
                    'data': {
                        'location': {'timezone': 'Asia/Shanghai'},
                        'hourly': [
                            {
                                'time': '2026-11-02T20:00',
                                'cloud_cover_percent': 10,
                                'cloud_cover_high_percent': 30,
                                'precipitation_probability': 0.2,
                            },
                            {'time': '2026-11-02T21:00', 'cloud_cover_percent': 10},
                        ],
                    },
                }
            },
        },
        '2026-11-02T00:00:00Z',
        '2026-11-02T00:01:00Z',
    )


@pytest.fixture
def observation():
    return {
        'site_id': 'test-site',
        'lat': 30,
        'lon': 120,
        'source': 'independent-station',
        'kind': 'observation',
        'valid_time': '2026-11-02T12:00:00Z',
        'cloud_definition': CLOUD_DEFINITION,
        'effective_cloud_percent': 40,
        'precipitation_occurred': False,
        'precipitation_definition': PRECIPITATION_DEFINITION,
    }


def test_exact_utc_pair_uses_layers_and_available_time_without_inventing_issue(
    snapshot, observation
):
    result = pair_snapshots([snapshot], [observation])
    assert result['unmatched_forecast_hours'] == 1
    assert result['verification']['matched_pairs'] == 1
    assert result['verification']['cloud_mae_percentage_points'] == 10
    assert result['verification']['rain_brier_score'] == pytest.approx(0.04)
    assert result['verification']['lead_time_basis'] == ['available_at']
    assert result['verification']['lead_hours'] == [pytest.approx(12 - 1 / 60)]
    assert result['pairs'][0]['forecast']['issued_at'] is None


@pytest.mark.parametrize(
    'field,value', [('site_id', 'elsewhere'), ('valid_time', '2026-11-02T12:01Z')]
)
def test_no_nearest_site_or_time_substitution(snapshot, observation, field, value):
    observation[field] = value
    result = pair_snapshots([snapshot], [observation])
    assert result['pairs'] == []
    assert result['verification']['cloud_mae_percentage_points'] is None


@pytest.mark.parametrize('kind', ['forecast', 'model_estimate'])
def test_model_results_are_not_truth(snapshot, observation, kind):
    observation['kind'] = kind
    result = pair_snapshots([snapshot], [observation])
    assert not result['pairs']
    assert result['rejected']


def test_no_self_verification_and_ambiguous_observations(snapshot, observation):
    observation['source'] = 'open-meteo'
    assert not pair_snapshots([snapshot], [observation])['pairs']
    observation['source'] = 'independent-station'
    result = pair_snapshots([snapshot], [observation, deepcopy(observation)])
    assert not result['pairs']
    assert result['rejected']


def test_duplicate_archives_do_not_multiply_samples(snapshot, observation):
    result = pair_snapshots([snapshot, deepcopy(snapshot)], [observation])
    assert result['verification']['matched_pairs'] == 1


def test_reused_site_label_cannot_hide_different_coordinates(snapshot, observation):
    observation['lat'] = 31
    result = pair_snapshots([snapshot], [observation])
    assert not result['pairs']
    assert result['rejected']


def test_rain_requires_matching_period_threshold_and_capture_before_period(snapshot, observation):
    observation['precipitation_definition'] = 'raining_at_timestamp'
    result = pair_snapshots([snapshot], [observation])
    assert result['verification']['rain_pairs'] == 0
    assert result['verification']['cloud_pairs'] == 1
    observation['precipitation_definition'] = PRECIPITATION_DEFINITION
    snapshot['retrieval_completed_at'] = '2026-11-02T11:30Z'
    result = pair_snapshots([snapshot], [observation])
    assert result['verification']['rain_pairs'] == 0
    assert result['verification']['cloud_pairs'] == 1


def test_late_capture_cannot_verify_past_forecast(snapshot, observation):
    snapshot['retrieval_completed_at'] = '2026-11-02T12:00Z'
    result = pair_snapshots([snapshot], [observation])
    assert result['excluded_nonfuture_hours'] == 1
    assert not result['pairs']


def test_different_cloud_definition_only_allows_comparable_rain(snapshot, observation):
    observation['cloud_definition'] = 'total_cloud_oktas'
    result = pair_snapshots([snapshot], [observation])
    assert result['verification']['cloud_pairs'] == 0
    assert result['verification']['rain_pairs'] == 1
    del observation['precipitation_occurred']
    result = pair_snapshots([snapshot], [observation])
    assert not result['pairs']
    assert result['rejected']


@pytest.mark.parametrize('value', [None, True, -1, float('inf'), 101, 10**1000])
def test_invalid_clouds_stay_unknown(snapshot, observation, value):
    hour = snapshot['weather']['providers']['open-meteo']['data']['hourly'][0]
    hour['cloud_cover_percent'] = value
    del hour['cloud_cover_high_percent']
    result = pair_snapshots([snapshot], [observation])
    assert result['verification']['cloud_pairs'] == 0
    assert result['verification']['rain_pairs'] == 1


@pytest.mark.parametrize('time', ['2026-11-01T01:00', '2026-03-08T02:00'])
def test_ambiguous_or_nonexistent_dst_hour_is_not_guessed(snapshot, observation, time):
    provider = snapshot['weather']['providers']['open-meteo']['data']
    provider['location']['timezone'] = 'America/New_York'
    provider['hourly'][0]['time'] = time
    result = pair_snapshots([snapshot], [observation])
    assert not result['pairs']
    assert result['rejected']


def test_duplicate_forecast_hours_rejected(snapshot, observation):
    hours = snapshot['weather']['providers']['open-meteo']['data']['hourly']
    hours.append(deepcopy(hours[0]))
    result = pair_snapshots([snapshot], [observation])
    assert not result['pairs']
    assert result['rejected']


def test_archives_are_separate_and_pair_cli_writes_explicit_report(snapshot, observation, tmp_path):
    first = write_snapshot(snapshot, tmp_path / 'captures')
    second = write_snapshot(snapshot, tmp_path / 'captures')
    assert first != second
    assert json.loads(first.read_text()) == snapshot
    observations = tmp_path / 'observations.json'
    observations.write_text(json.dumps([observation]))
    output = tmp_path / 'output'
    assert (
        main(
            [
                'pair',
                '--archives',
                str(first),
                str(second),
                '--observations',
                str(observations),
                '--out-dir',
                str(output),
            ]
        )
        == 0
    )
    assert len(json.loads((output / 'forecast-pairs.json').read_text())) == 1
    assert (
        json.loads((output / 'forecast-pairing.json').read_text())['verification']['matched_pairs']
        == 1
    )


@pytest.mark.parametrize(
    'site_id,start,end',
    [
        ('', '2026-11-02T00:00Z', '2026-11-02T00:01Z'),
        ('site', '2026-11-02T00:00', '2026-11-02T00:01Z'),
        ('site', '2026-11-02T00:02Z', '2026-11-02T00:01Z'),
    ],
)
def test_capture_requires_identity_and_ordered_aware_times(site_id, start, end):
    with pytest.raises(ValueError):
        make_snapshot(site_id, {}, start, end)


def test_capture_cli_preserves_provider_payload_without_claiming_observations(
    snapshot, monkeypatch, tmp_path
):
    calls = []

    def fetch(*args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(model_dump=lambda **_: snapshot['weather'])

    monkeypatch.setattr('src.functions.weather.service.get_aggregated_weather_by_position', fetch)
    assert (
        main(
            [
                'capture',
                '--site-id',
                'station',
                '--lat',
                '30',
                '--lon',
                '120',
                '--timezone',
                'Asia/Shanghai',
                '--out-dir',
                str(tmp_path),
            ]
        )
        == 0
    )
    [path] = tmp_path.glob('forecast-*.json')
    captured = json.loads(path.read_text())
    assert captured['weather'] == snapshot['weather']
    assert captured['site_id'] == 'station'
    assert calls == [((30.0, 120.0), {'provider': 'open-meteo', 'timezone': 'Asia/Shanghai'})]


def test_missing_observations_never_yield_an_accuracy_result(snapshot):
    result = pair_snapshots([snapshot], [])
    assert result['verification']['matched_pairs'] == 0
    assert result['verification']['cloud_mae_percentage_points'] is None
    assert result['verification']['rain_brier_score'] is None
