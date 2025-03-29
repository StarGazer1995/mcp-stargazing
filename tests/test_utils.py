import pytest
from src.utils import validate_coordinates, create_earth_location, parse_datetime, localtime_to_utc
from astropy.coordinates import EarthLocation
from datetime import datetime
import pytz

UTC=pytz.timezone("UTC")

def test_validate_coordinates():
    assert validate_coordinates(40.7128, -74.0060) is True
    assert validate_coordinates(0, 0) is True
    assert validate_coordinates(-90, 180) is True
    assert validate_coordinates(91, -74.0060) is False

def test_create_earth_location():
    loc = create_earth_location(40.7128, -74.0060)
    assert isinstance(loc, EarthLocation)
    assert abs(loc.lat.deg - 40.7128) < 1e-5
    assert abs(loc.lon.deg - -74.0060) < 1e-5
    with pytest.raises(ValueError):
        create_earth_location(100, -200)

def test_parse_datetime():
    dt = parse_datetime("2023-10-01", "America/New_York")
    assert isinstance(dt, datetime)
    assert dt.year == 2023
    assert dt.month == 10
    assert dt.day == 1
    assert dt.tzinfo.zone == "UTC"

def test_localtime_to_utc():
    local_dt = parse_datetime("2023-10-01", "America/New_York")
    utc_dt = localtime_to_utc(local_dt)
    assert utc_dt.tzinfo == pytz.UTC
    assert utc_dt.hour == local_dt.hour
    with pytest.raises(ValueError):
        localtime_to_utc(datetime(2023, 10, 1))

if __name__ == "__main__":
    pytest.main()