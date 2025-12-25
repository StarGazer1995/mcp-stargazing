import pytest
from datetime import datetime
import pytz
from src.celestial import calculate_moon_info

@pytest.mark.asyncio
async def test_moon_phase_accuracy():
    # Known Full Moon: Jan 25, 2024, ~17:54 UTC
    full_moon_date = datetime(2024, 1, 25, 17, 54, tzinfo=pytz.UTC)
    info = calculate_moon_info(full_moon_date)
    
    # Allow for some margin in phase name transition or exact timing
    # But specifically at peak full moon it should be Full Moon
    print(f"DEBUG: Calculated info for Full Moon: {info}")
    assert info["phase_name"] == "Full Moon"
    assert info["illumination"] > 0.99

    # Known New Moon: Jan 11, 2024, ~11:57 UTC
    new_moon_date = datetime(2024, 1, 11, 11, 57, tzinfo=pytz.UTC)
    info = calculate_moon_info(new_moon_date)
    print(f"DEBUG: Calculated info for New Moon: {info}")
    assert info["phase_name"] == "New Moon"
    assert info["illumination"] < 0.01

    # Test First Quarter: Jan 18, 2024
    fq_date = datetime(2024, 1, 18, 4, 0, tzinfo=pytz.UTC)
    info = calculate_moon_info(fq_date)
    print(f"DEBUG: Calculated info for First Quarter: {info}")
    # Illumination should be around 50%
    assert 0.4 < info["illumination"] < 0.6
