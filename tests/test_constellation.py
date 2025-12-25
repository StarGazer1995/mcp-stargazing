import pytest
from datetime import datetime
import pytz
from src.celestial import get_constellation_center
from src.utils import create_earth_location

@pytest.mark.asyncio
async def test_constellation_center():
    # Test Location: Greenwich
    loc = create_earth_location(lat=51.4769, lon=0.0)
    
    # Test Time: Winter night in Northern Hemisphere (Orion should be visible)
    # Jan 15, 2024, 22:00 UTC
    # Note: Orion Nebula is RA 05h 35m, Dec -05d 23m.
    # At 22:00 UTC in Jan, it should be visible.
    
    time_val = datetime(2024, 1, 15, 22, 0, tzinfo=pytz.UTC)
    
    # Let's try a simpler target: The Sun.
    # At 22:00 UTC in Jan in London, Sun should be definitely DOWN (negative altitude).
    # Sun RA ~19h.
    
    from src.celestial import celestial_pos
    sun_alt, sun_az = celestial_pos("sun", loc, time_val)
    print(f"DEBUG: Sun position: Alt={sun_alt}, Az={sun_az}")
    # If Sun is up, our time/loc logic is broken.
    assert sun_alt < 0 
    
    # Let's try a different constellation/star that is definitely circumpolar.
    # Polaris. RA ~2.5h, Dec +89.
    # Always Alt ~ Lat (51 deg).
    polaris = get_constellation_center("Polaris", loc, time_val)
    print(f"DEBUG: Polaris position: {polaris}")
    assert polaris["altitude"] > 40
    assert polaris["altitude"] < 60
    
    # Let's try finding the constellation "Ursa Minor".
    ursa_minor = get_constellation_center("Ursa Minor", loc, time_val)
    print(f"DEBUG: Ursa Minor position: {ursa_minor}")
    assert ursa_minor["altitude"] > 0

