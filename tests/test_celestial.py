from datetime import datetime

import astropy.units as u
import pytest
import pytz
from astropy.coordinates import EarthLocation, SkyCoord
from astropy.time import Time

import src.celestial as celestial_module
from src.celestial import (
    _generate_time_grid,
    _get_celestial_object,
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


def test_calculate_rise_set_deepspace():
    """Test rise/set for deep-space objects (may not rise/set)."""
    date = UTC.localize(datetime(2023, 10, 1))
    rise, set_ = celestial_rise_set('andromeda', NYC, date)
    assert rise is not None or set_ is not None


def test_calculate_rise_set_invalid_horizon():
    """Test invalid horizon elevation."""
    with pytest.raises(ValueError, match='Horizon must be between'):
        celestial_rise_set('sun', NYC, datetime(2023, 10, 1), horizon=100)


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
    """对象资源缺失时应降级为空列表并打印提示。"""
    original_cache = celestial_module.OBJECTS_CACHE
    celestial_module.OBJECTS_CACHE = None

    monkeypatch.setattr(
        celestial_module,
        '_load_data_resource',
        lambda filename: (_ for _ in ()).throw(FileNotFoundError(filename)),
    )

    try:
        assert celestial_module._load_objects() == []
        captured = capsys.readouterr()
        assert 'objects.json' in captured.out
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
