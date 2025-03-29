import pytest
from src.celestial import (
    celestial_pos,
    celestial_rise_set,
    _get_celestial_object,
    _generate_time_grid
)
from astropy.time import Time
from datetime import datetime, timedelta
from astropy.coordinates import EarthLocation, SkyCoord
import pytz
import astropy.units as u
import numpy as np

# Test data
NYC = EarthLocation(lat=40.7128*u.deg, lon=-74.0060*u.deg)
UTC = pytz.timezone(zone='America/New_York')

def test_calculate_altitude_sun():
    """Test position calculation for the Sun at a known time."""
    time = datetime(2023, 6, 22, 13, 0, 0)
    time = UTC.localize(time)
    altitude, _ = celestial_pos("sun", NYC, time)
    assert 72 <= altitude <= 75
def test_calculate_altitude_moon():
    """Test position calculation for the Moon."""
    time = datetime(2023, 10, 1, 18, 0, 0)
    time = UTC.localize(time)
    altitude, _ = celestial_pos("moon", NYC, time)
    assert -90 <= altitude <= 90
def test_calculate_altitude_deepspace():
    """Test position calculation for deep-space objects (e.g., Andromeda)."""
    time = Time(datetime.now())
    altitude, _ = celestial_pos("andromeda", NYC, time)
    assert -90 <= altitude <= 90

def test_calculate_altitude_invalid_object():
    """Test error handling for unsupported objects."""
    with pytest.raises(ValueError, match="Failed to resolve object"):
        celestial_pos("invalid_object", NYC, Time.now())

def test_calculate_rise_set_sun():
    """Test rise/set calculation for the Sun (should rise and set)."""
    date = UTC.localize(datetime(2023, 10, 1))
    rise, set_ = celestial_rise_set("sun", NYC, date)
    assert rise is not None and set_ is not None
    assert rise < set_

def test_calculate_rise_set_deepspace():
    """Test rise/set for deep-space objects (may not rise/set)."""
    date = UTC.localize(datetime(2023, 10, 1))
    rise, set_ = celestial_rise_set("andromeda", NYC, date)
    assert rise is not None or set_ is not None

def test_calculate_rise_set_invalid_horizon():
    """Test invalid horizon elevation."""
    with pytest.raises(ValueError, match="Horizon must be between"):
        celestial_rise_set("sun", NYC, datetime(2023, 10, 1), horizon=100)

def test__get_celestial_object():
    """Test resolving celestial objects to SkyCoord."""
    time = Time.now()
    assert isinstance(_get_celestial_object("sun", time), SkyCoord)
    assert isinstance(_get_celestial_object("Moon", time), SkyCoord)
    assert isinstance(_get_celestial_object("Mars", time), SkyCoord)
    assert isinstance(_get_celestial_object("andromeda", time), SkyCoord)
    assert isinstance(_get_celestial_object("sirius", time), SkyCoord)
def test__generate_time_grid():
    """Test time grid generation (5-minute intervals over 24h)."""
    date = UTC.localize(datetime(2023, 10, 1))
    time_grid = _generate_time_grid(date)
    assert len(time_grid) == 288
    assert abs((time_grid[-1] - time_grid[0]).to_datetime().total_seconds() / 3600 - 24) < 1e-3

if __name__ == "__main__":
    pytest.main()
