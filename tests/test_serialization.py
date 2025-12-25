import pytest
import asyncio
from unittest.mock import MagicMock, patch
from datetime import datetime
import pytz
from src.functions.celestial.impl import get_celestial_rise_set, get_celestial_pos
from src.functions.places.impl import analysis_area

def test_celestial_rise_set_serialization():
    """Test that get_celestial_rise_set returns ISO strings, not datetime objects."""
    
    async def run_test():
        # Mock return values from process_location_and_time and celestial_rise_set
        with patch('src.functions.celestial.impl.process_location_and_time') as mock_process, \
             patch('src.functions.celestial.impl.celestial_rise_set') as mock_calc:
            
            # Setup mocks
            mock_process.return_value = (MagicMock(), MagicMock())
            
            tz = pytz.timezone("America/New_York")
            rise = tz.localize(datetime(2023, 1, 1, 10, 0, 0))
            set_ = tz.localize(datetime(2023, 1, 1, 20, 0, 0))
            mock_calc.return_value = (rise, set_)
            
            # Use .fn to access the underlying async function
            result = await get_celestial_rise_set.fn(
                celestial_object="sun",
                lon=-74.0,
                lat=40.0,
                time="2023-01-01 12:00:00",
                time_zone="America/New_York"
            )
            
            assert isinstance(result, dict)
            # Check for new response format
            assert "data" in result
            assert "_meta" in result
            data = result["data"]
            assert isinstance(data["rise_time"], str)
            assert isinstance(data["set_time"], str)
            assert "T" in data["rise_time"]
            
    asyncio.run(run_test())

def test_celestial_pos_serialization():
    """Test that get_celestial_pos returns simple floats."""
    async def run_test():
        with patch('src.functions.celestial.impl.process_location_and_time') as mock_process, \
             patch('src.functions.celestial.impl.celestial_pos') as mock_calc:
            
            mock_process.return_value = (MagicMock(), MagicMock())
            mock_calc.return_value = (45.5, 180.0)
            
            result = await get_celestial_pos.fn(
                celestial_object="sun",
                lon=-74.0,
                lat=40.0,
                time="2023-01-01 12:00:00",
                time_zone="America/New_York"
            )
            
            assert isinstance(result, dict)
            # Check for new response format
            assert "data" in result
            data = result["data"]
            assert isinstance(data["altitude"], float)
            assert isinstance(data["azimuth"], float)
            assert data["altitude"] == 45.5

    asyncio.run(run_test())

def test_analysis_area_pagination_serialization():
    """Test analysis_area pagination and result serialization."""
    
    class MockCache:
        def __init__(self):
            self.store = {}
        def get(self, key):
            return self.store.get(key)
        def set(self, key, value):
            self.store[key] = value

    async def run_test():
        # Mock StargazingPlaceFinder
        with patch('src.functions.places.impl.StargazingPlaceFinder') as MockPF, \
             patch('src.functions.places.impl.ANALYSIS_CACHE', new=MockCache()) as mock_cache: 
            
            mock_instance = MockPF.return_value
            mock_results = [{"name": f"Loc {i}", "score": i} for i in range(25)]
            mock_instance.analyze_area.return_value = mock_results
            
            # Test Page 1 (size 10)
            result_p1 = await analysis_area.fn(
                south=30, west=100, north=31, east=101,
                page=1, page_size=10
            )
            
            assert "data" in result_p1
            data_p1 = result_p1["data"]
            
            assert data_p1["page"] == 1
            assert data_p1["total"] == 25
            assert len(data_p1["items"]) == 10
            assert data_p1["items"][0]["name"] == "Loc 0"
            
            # Test Page 3 (size 10, should have 5 items)
            result_p3 = await analysis_area.fn(
                south=30, west=100, north=31, east=101,
                page=3, page_size=10
            )
            
            data_p3 = result_p3["data"]
            assert data_p3["page"] == 3
            assert len(data_p3["items"]) == 5
            assert data_p3["items"][0]["name"] == "Loc 20"
            
            # Verify cache was used (mock_instance called only once)
            assert MockPF.call_count == 1
            
    asyncio.run(run_test())
