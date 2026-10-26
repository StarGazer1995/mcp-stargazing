"""Tests for the stargazing-core spatial weather adapter."""

from datetime import UTC, datetime

import numpy as np
from stargazing_core import WeatherModel

from src.functions.weather import spatial


def test_nearest_valid_time_index_uses_requested_time():
    valid_times = ['2026-10-25T00:00:00Z', '2026-10-25T06:00:00Z']

    assert (
        spatial._nearest_valid_time_index(valid_times, datetime(2026, 10, 25, 5, tzinfo=UTC)) == 1
    )


def test_spatial_time_helpers_handle_naive_and_empty_inputs():
    assert spatial._parse_valid_time('2026-10-25T00:00:00').tzinfo == UTC

    try:
        spatial._nearest_valid_time_index([], datetime(2026, 10, 25, tzinfo=UTC))
    except ValueError as exc:
        assert 'no valid times' in str(exc)
    else:
        raise AssertionError('empty valid times should fail clearly')


def test_read_spatial_weather_samples_candidate_points(monkeypatch):
    class FakeReader:
        model = WeatherModel.DWD_ICON
        valid_times = ['2026-10-25T00:00:00Z']

        def read_window(self, *_args, **_kwargs):
            return np.array([[10.0, 20.0], [30.0, 40.0]], dtype=np.float32)

    monkeypatch.setattr(spatial, 'OmWeatherReader', lambda _model: FakeReader())

    result = spatial._read_spatial_weather(
        south=40.0,
        west=116.0,
        north=41.0,
        east=117.0,
        time='2026-10-25 08:00:00',
        time_zone='Asia/Shanghai',
        locations=[
            {'lat': 41.0, 'lon': 116.0},
            {'lat': 40.0, 'lon': 117.0},
        ],
    )

    assert result['model'] == 'dwd_icon'
    assert result['valid_time'] == '2026-10-25T00:00:00Z'
    assert result['samples'] == [
        {'cloud_cover_percent': 10.0},
        {'cloud_cover_percent': 40.0},
    ]
