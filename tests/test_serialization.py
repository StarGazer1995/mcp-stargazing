import asyncio
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
import pytz

from src.functions.celestial.impl import get_celestial_pos, get_celestial_rise_set
from src.functions.places.impl import analysis_area


def test_celestial_rise_set_serialization():
    """Test that get_celestial_rise_set returns ISO strings, not datetime objects."""

    async def run_test():
        # Mock return values from process_location_and_time and celestial_rise_set
        with (
            patch('src.functions.celestial.impl.process_location_and_time') as mock_process,
            patch('src.functions.celestial.impl.celestial_rise_set') as mock_calc,
        ):
            # Setup mocks
            mock_process.return_value = (MagicMock(), MagicMock())

            tz = pytz.timezone('America/New_York')
            rise = tz.localize(datetime(2023, 1, 1, 10, 0, 0))
            set_ = tz.localize(datetime(2023, 1, 1, 20, 0, 0))
            mock_calc.return_value = (rise, set_)

            # Use .fn to access the underlying async function
            result = await get_celestial_rise_set.fn(
                celestial_object='sun',
                lon=-74.0,
                lat=40.0,
                time='2023-01-01 12:00:00',
                time_zone='America/New_York',
            )

            assert isinstance(result, dict)
            # Check for new response format
            assert 'data' in result
            assert '_meta' in result
            data = result['data']
            assert isinstance(data['rise_time'], str)
            assert isinstance(data['set_time'], str)
            assert 'T' in data['rise_time']

    asyncio.run(run_test())


def test_celestial_pos_serialization():
    """Test that get_celestial_pos returns simple floats."""

    async def run_test():
        with (
            patch('src.functions.celestial.impl.process_location_and_time') as mock_process,
            patch('src.functions.celestial.impl.celestial_pos') as mock_calc,
        ):
            mock_process.return_value = (MagicMock(), MagicMock())
            mock_calc.return_value = (45.5, 180.0)

            result = await get_celestial_pos.fn(
                celestial_object='sun',
                lon=-74.0,
                lat=40.0,
                time='2023-01-01 12:00:00',
                time_zone='America/New_York',
            )

            assert isinstance(result, dict)
            # Check for new response format
            assert 'data' in result
            data = result['data']
            assert isinstance(data['altitude'], float)
            assert isinstance(data['azimuth'], float)
            assert data['altitude'] == 45.5

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
        with (
            patch('src.functions.places.impl.StargazingPlaceFinder') as MockPF,
            patch('src.functions.places.impl.ANALYSIS_CACHE', new=MockCache()),
        ):
            mock_instance = MockPF.return_value
            mock_results = [
                {'name': f'Loc {i}', 'score': i, 'lat': 35.0 + i * 0.01, 'lon': -120.0 - i * 0.01}
                for i in range(25)
            ]
            mock_instance.analyze_area.return_value = mock_results

            # Test Page 1 (size 10)
            result_p1 = await analysis_area.fn(
                south=30, west=100, north=31, east=101, page=1, page_size=10
            )

            assert 'data' in result_p1
            data_p1 = result_p1['data']

            assert data_p1['page'] == 1
            assert data_p1['total'] == 25
            assert len(data_p1['items']) == 10
            assert data_p1['items'][0]['name'] == 'Loc 0'

            # Test Page 3 (size 10, should have 5 items)
            result_p3 = await analysis_area.fn(
                south=30, west=100, north=31, east=101, page=3, page_size=10
            )

            data_p3 = result_p3['data']
            assert data_p3['page'] == 3
            assert len(data_p3['items']) == 5
            assert data_p3['items'][0]['name'] == 'Loc 20'

            # Verify cache was used (mock_instance called only once)
            assert MockPF.call_count == 1

    asyncio.run(run_test())


@pytest.mark.asyncio
async def test_analysis_area_resource_id_is_stable_across_pages():
    """The same non-pagination query should reuse the same cached resource identifier."""

    class MockCache:
        def __init__(self):
            self.store = {}

        def get(self, key):
            return self.store.get(key)

        def set(self, key, value):
            self.store[key] = value

    with (
        patch('src.functions.places.impl.StargazingPlaceFinder') as mock_placefinder,
        patch('src.functions.places.impl.ANALYSIS_CACHE', new=MockCache()),
    ):
        mock_placefinder.return_value.analyze_area.return_value = [
            {'name': f'Loc {i}', 'score': i, 'lat': 35.0 + i * 0.01, 'lon': -120.0 - i * 0.01}
            for i in range(12)
        ]

        result_page_1 = await analysis_area.fn(
            south=30.0,
            west=100.0,
            north=31.0,
            east=101.0,
            page=1,
            page_size=5,
        )
        result_page_2 = await analysis_area.fn(
            south=30.0,
            west=100.0,
            north=31.0,
            east=101.0,
            page=2,
            page_size=5,
        )

    assert result_page_1['_meta']['status'] == 'success'
    assert result_page_2['_meta']['status'] == 'success'
    assert result_page_1['data']['resource_id'] == result_page_2['data']['resource_id']
    assert mock_placefinder.call_count == 1


@pytest.mark.asyncio
async def test_analysis_area_resource_id_changes_with_calc_params():
    """Changing a calculation parameter should produce a distinct resource identifier."""

    class MockCache:
        def get(self, key):
            return None

        def set(self, key, value):
            return None

    with (
        patch('src.functions.places.impl.StargazingPlaceFinder') as mock_placefinder,
        patch('src.functions.places.impl.ANALYSIS_CACHE', new=MockCache()),
    ):
        mock_placefinder.return_value.analyze_area.return_value = []

        result_a = await analysis_area.fn(
            south=30.0,
            west=100.0,
            north=31.0,
            east=101.0,
            min_height_diff=100.0,
        )
        result_b = await analysis_area.fn(
            south=30.0,
            west=100.0,
            north=31.0,
            east=101.0,
            min_height_diff=150.0,
        )

    assert result_a['_meta']['status'] == 'success'
    assert result_b['_meta']['status'] == 'success'
    assert result_a['data']['resource_id'] != result_b['data']['resource_id']


@pytest.mark.asyncio
async def test_analysis_area_returns_empty_items_for_out_of_range_page():
    """Out-of-range pages should remain successful and return an empty item list."""

    class MockCache:
        def __init__(self):
            self.store = {}

        def get(self, key):
            return self.store.get(key)

        def set(self, key, value):
            self.store[key] = value

    with (
        patch('src.functions.places.impl.StargazingPlaceFinder') as mock_placefinder,
        patch('src.functions.places.impl.ANALYSIS_CACHE', new=MockCache()),
    ):
        mock_placefinder.return_value.analyze_area.return_value = [
            {'name': f'Loc {i}', 'score': i, 'lat': 35.0 + i * 0.01, 'lon': -120.0 - i * 0.01}
            for i in range(3)
        ]

        result = await analysis_area.fn(
            south=30.0,
            west=100.0,
            north=31.0,
            east=101.0,
            page=5,
            page_size=2,
        )

    assert result['_meta']['status'] == 'success'
    assert result['data']['items'] == []
    assert result['data']['total'] == 3
    assert result['data']['total_pages'] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('field_name', 'field_value', 'expected_message'),
    [
        ('page', 0, 'page must be greater than or equal to 1.'),
        ('page_size', 0, 'page_size must be greater than or equal to 1.'),
    ],
)
async def test_analysis_area_rejects_invalid_pagination_inputs(
    field_name: str,
    field_value: int,
    expected_message: str,
):
    """Invalid pagination inputs should return the standard structured error payload."""
    kwargs = {
        'south': 30.0,
        'west': 100.0,
        'north': 31.0,
        'east': 101.0,
        'page': 1,
        'page_size': 10,
    }
    kwargs[field_name] = field_value

    result = await analysis_area.fn(**kwargs)

    assert result['_meta']['status'] == 'error'
    assert result['error']['code'] == 'CONFIGURATION_ERROR'
    assert result['error']['message'] == expected_message
    assert result['error']['details'] == {field_name: field_value}
