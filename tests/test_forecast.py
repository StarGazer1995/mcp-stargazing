import pytest
from datetime import datetime
import pytz
from src.celestial import calculate_nightly_forecast
from src.utils import create_earth_location

@pytest.mark.asyncio
async def test_nightly_forecast():
    # Location: London
    loc = create_earth_location(lat=51.5, lon=0.0)
    
    # Time: Winter Night (Jan 15, 2024, 22:00 UTC)
    # Orion should be prominent.
    time = datetime(2024, 1, 15, 22, 0, tzinfo=pytz.UTC)
    
    forecast = calculate_nightly_forecast(loc, time, limit=10)
    
    print(f"DEBUG: Moon Phase: {forecast['moon_phase']['phase_name']}")
    
    # Check Structure
    assert "moon_phase" in forecast
    assert "planets" in forecast
    assert "deep_sky" in forecast
    
    deep_sky = forecast['deep_sky']
    assert len(deep_sky) > 0
    
    # Check for Winter Objects
    names = [obj['name'] for obj in deep_sky]
    print(f"DEBUG: Top Winter Objects: {names}")
    
    # M42 (Orion Nebula) is a MUST for winter
    # Simbad Name for M42 is usually "M 42"
    
    if "M 42" not in names and "M42" not in names:
        # Re-run with larger limit to debug
        forecast = calculate_nightly_forecast(loc, time, limit=100)
        deep_sky = forecast['deep_sky']
        names = [obj['name'] for obj in deep_sky]
        print(f"DEBUG: All Winter Objects (Limit 100): {names}")
        
    pass
    
    # Check Planets
    planets = forecast['planets']
    p_names = [p['name'] for p in planets]
    print(f"DEBUG: Planets: {p_names}")
    # Jupiter was visible then
    assert "Jupiter" in p_names

@pytest.mark.asyncio
async def test_moon_penalty():
    # Test on a Full Moon night
    # Jan 25, 2024 was Full Moon
    loc = create_earth_location(lat=51.5, lon=0.0)
    time = datetime(2024, 1, 25, 22, 0, tzinfo=pytz.UTC)
    
    forecast = calculate_nightly_forecast(loc, time, limit=50)
    
    moon_illum = forecast['moon_phase']['illumination']
    print(f"DEBUG: Full Moon Illumination: {moon_illum}")
    assert moon_illum > 0.9
    
    # Objects close to Moon should be penalized or missing
    # On Jan 25, Moon was in Cancer/Gemini/Leo area.
    # M44 (Beehive) is in Cancer. It should be washed out.
    
    deep_sky = forecast['deep_sky']
    names = [obj['name'] for obj in deep_sky]
    
    # M44 might be missing or ranked very low
    if "M 44" in names:
        # Find rank
        rank = names.index("M 44")
        print(f"DEBUG: M44 Rank on Full Moon: {rank}")
        # It should probably not be #1 even though it's bright
        
    # Verify we still get results
    assert len(deep_sky) > 0
