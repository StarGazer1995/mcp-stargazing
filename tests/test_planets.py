import pytest
from datetime import datetime
import pytz
from src.celestial import get_visible_planets
from src.utils import create_earth_location

@pytest.mark.asyncio
async def test_visible_planets_logic():
    # Test Location: Greenwich, London
    loc = create_earth_location(lat=51.4769, lon=0.0)
    
    # Test Date: Noon UTC (Sun should be high, planets vary)
    # Actually, let's pick a date/time where we know Jupiter is visible at night
    # Jan 25, 2024, 22:00 UTC. Jupiter was high in the sky in London.
    time = datetime(2024, 1, 25, 22, 0, tzinfo=pytz.UTC)
    
    planets = get_visible_planets(loc, time)
    
    print(f"DEBUG: Visible planets at {time}: {planets}")
    
    # Extract names
    names = [p["name"] for p in planets]
    
    # Jupiter should be visible
    assert "Jupiter" in names
    
    # Check structure
    first = planets[0]
    assert "altitude" in first
    assert "azimuth" in first
    assert first["altitude"] > 0

@pytest.mark.asyncio
async def test_visible_planets_none_visible():
    # Theoretical test: if we check at noon, most planets might be washed out by sun visually, 
    # but 'get_visible_planets' returns geometrical visibility (altitude > 0).
    # So we can't easily assert "none visible" without picking a very specific time/place.
    # Instead, let's verify that altitudes are positive.
    
    loc = create_earth_location(lat=0, lon=0)
    time = datetime(2024, 1, 1, 12, 0, tzinfo=pytz.UTC)
    planets = get_visible_planets(loc, time)
    
    for p in planets:
        assert p["altitude"] > 0
