from datetime import datetime, timedelta, timezone

import astropy.units as u
import numpy as np
import pytest
import pytz
from astropy.coordinates import EarthLocation, SkyCoord
from astropy.time import Time

import src.celestial as celestial_module
from src.celestial import (
    _find_rise_set_indices,
    _generate_time_grid,
    _get_celestial_object,
    calculate_civil_night_window,
    celestial_pos,
    celestial_rise_set,
)

# Test data
NYC = EarthLocation(lat=40.7128 * u.deg, lon=-74.0060 * u.deg)
UTC = pytz.timezone(zone='America/New_York')


def test_calculate_altitude_sun():
    """Test position calculation for the Sun at a known time."""
    time = datetime(2023, 6, 22, 13, 0, 0)
    time = UTC.localize(time)
    altitude, _ = celestial_pos('sun', NYC, time)
    assert 72 <= altitude <= 75


def test_calculate_altitude_moon():
    """Test position calculation for the Moon."""
    time = datetime(2023, 10, 1, 18, 0, 0)
    time = UTC.localize(time)
    altitude, _ = celestial_pos('moon', NYC, time)
    assert -90 <= altitude <= 90


def test_calculate_altitude_deepspace():
    """Test position calculation for deep-space objects (e.g., Andromeda)."""
    time = Time(datetime(2024, 1, 15, 22, 0, tzinfo=pytz.UTC))
    altitude, _ = celestial_pos('andromeda', NYC, time)
    assert -90 <= altitude <= 90


def test_calculate_altitude_invalid_object():
    """Test error handling for unsupported objects."""
    with pytest.raises(ValueError, match='Failed to resolve object'):
        celestial_pos('invalid_object', NYC, Time.now())


def test_calculate_rise_set_sun():
    """Test rise/set calculation for the Sun (should rise and set)."""
    date = UTC.localize(datetime(2023, 10, 1))
    rise, set_ = celestial_rise_set('sun', NYC, date)
    assert rise is not None and set_ is not None
    assert rise < set_


def test_calculate_rise_set_sun_next_events_crosses_midnight():
    """Next-event mode should roll a late-night request into the following day."""
    reference = UTC.localize(datetime(2023, 10, 1, 23, 0))

    rise, set_ = celestial_rise_set('sun', NYC, reference, event_scope='next_events')

    assert rise is not None and set_ is not None
    assert rise > reference
    assert set_ > reference
    assert rise.date() == reference.date() + timedelta(days=1)


def test_calculate_rise_set_deepspace():
    """Test rise/set for deep-space objects (may not rise/set)."""
    date = UTC.localize(datetime(2023, 10, 1))
    rise, set_ = celestial_rise_set('andromeda', NYC, date)
    assert rise is not None or set_ is not None


def test_calculate_rise_set_invalid_horizon():
    """Test invalid horizon elevation."""
    with pytest.raises(ValueError, match='Horizon must be between'):
        celestial_rise_set('sun', NYC, datetime(2023, 10, 1), horizon=100)


def test_calculate_rise_set_invalid_event_scope():
    """Unknown event scopes should fail explicitly instead of silently changing semantics."""
    with pytest.raises(ValueError, match='event_scope'):
        celestial_rise_set(
            'sun',
            NYC,
            UTC.localize(datetime(2023, 10, 1)),
            event_scope='tomorrow_only',
        )


def test_calculate_civil_night_window_contains_late_night_reference():
    """A late-night reference should stay inside the current dusk-to-dawn window."""
    reference = UTC.localize(datetime(2024, 10, 1, 23, 0))

    window = calculate_civil_night_window(NYC, reference)

    dusk = datetime.fromisoformat(window.civil_dusk)
    dawn = datetime.fromisoformat(window.civil_dawn)
    assert dusk < reference < dawn
    assert window.local_date == '2024-10-01'
    assert window.duration_hours > 0


def test_calculate_civil_night_window_from_noon_chooses_upcoming_night():
    """A daytime reference should select the next dusk and following dawn."""
    reference = UTC.localize(datetime(2024, 10, 1, 12, 0))

    window = calculate_civil_night_window(NYC, reference)

    dusk = datetime.fromisoformat(window.civil_dusk)
    dawn = datetime.fromisoformat(window.civil_dawn)
    assert reference < dusk < dawn
    assert window.local_date == '2024-10-01'


def test_calculate_civil_night_window_requires_timezone():
    with pytest.raises(ValueError, match='timezone-aware'):
        calculate_civil_night_window(NYC, datetime(2024, 10, 1, 23, 0))


def test_calculate_civil_night_window_accepts_fixed_offset_timezone():
    reference = datetime(2024, 10, 1, 23, 0, tzinfo=timezone(timedelta(hours=8)))
    observer = EarthLocation(lat=30.0 * u.deg, lon=120.0 * u.deg)

    window = calculate_civil_night_window(observer, reference)

    assert datetime.fromisoformat(window.civil_dusk) < reference
    assert datetime.fromisoformat(window.civil_dawn) > reference
    assert window.time_zone == 'UTC+08:00'


def test_calculate_civil_night_window_rejects_missing_crossings():
    reference = UTC.localize(datetime(2024, 10, 1, 12, 0))

    with pytest.raises(ValueError, match='No civil-dark window'):
        calculate_civil_night_window(NYC, reference, civil_horizon=90.0)


def test__get_celestial_object():
    """Test resolving celestial objects to SkyCoord."""
    time = Time.now()
    assert isinstance(_get_celestial_object('sun', time), SkyCoord)
    assert isinstance(_get_celestial_object('Moon', time), SkyCoord)
    assert isinstance(_get_celestial_object('Mars', time), SkyCoord)
    assert isinstance(_get_celestial_object('andromeda', time), SkyCoord)
    assert isinstance(_get_celestial_object('sirius', time), SkyCoord)


def test__generate_time_grid():
    """Test time grid generation (5-minute intervals over 24h)."""
    date = UTC.localize(datetime(2023, 10, 1))
    time_grid = _generate_time_grid(date)
    assert len(time_grid) == 288
    assert abs((time_grid[-1] - time_grid[0]).to_datetime().total_seconds() / 3600 - 24) < 1e-3


def test_find_rise_set_indices_distinguishes_rise_from_set():
    """下降穿越与上升穿越应分别映射为 set / rise。"""
    altitudes = np.array([-5.0, -1.0, 2.0, 4.0, 1.0, -2.0])

    rise_idx, set_idx = _find_rise_set_indices(altitudes, horizon=0.0)

    assert rise_idx == 1
    assert set_idx == 4


def test_load_data_resource_reads_packaged_json(monkeypatch):
    """打包资源读取应通过 `importlib.resources` 成功解析 JSON。"""

    class FakeResource:
        def read_text(self, encoding='utf-8'):
            assert encoding == 'utf-8'
            return '[{"name": "M42"}]'

    class FakeDataDir:
        def joinpath(self, name):
            assert name == 'objects.json'
            return FakeResource()

    class FakePackageRoot:
        def joinpath(self, name):
            assert name == 'data'
            return FakeDataDir()

    monkeypatch.setattr(
        celestial_module.resources,
        'files',
        lambda package_name: FakePackageRoot(),
    )

    assert celestial_module._load_data_resource('objects.json') == [{'name': 'M42'}]


def test_load_objects_returns_empty_list_when_resource_missing(monkeypatch, capsys):
    """对象资源缺失时应降级为空列表并记录警告。"""
    original_cache = celestial_module.OBJECTS_CACHE
    celestial_module.OBJECTS_CACHE = None

    monkeypatch.setattr(
        celestial_module,
        '_load_data_resource',
        lambda filename: (_ for _ in ()).throw(FileNotFoundError(filename)),
    )

    try:
        assert celestial_module._load_objects() == []
        assert 'objects.json' in capsys.readouterr().out
    finally:
        celestial_module.OBJECTS_CACHE = original_cache


def test_load_constellation_centers_returns_empty_list_when_resource_missing(monkeypatch):
    """星座中心资源缺失时应降级为空列表。"""
    original_cache = celestial_module.CONSTELLATIONS_CACHE
    celestial_module.CONSTELLATIONS_CACHE = None

    monkeypatch.setattr(
        celestial_module,
        '_load_data_resource',
        lambda filename: (_ for _ in ()).throw(FileNotFoundError(filename)),
    )

    try:
        assert celestial_module._load_constellation_centers() == []
    finally:
        celestial_module.CONSTELLATIONS_CACHE = original_cache


if __name__ == '__main__':
    pytest.main()
