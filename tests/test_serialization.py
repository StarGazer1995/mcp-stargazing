import asyncio
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
import pytz

from src.functions.celestial.impl import get_celestial_pos, get_celestial_rise_set
from src.functions.places.impl import analysis_area
from src.functions.planning.impl import get_best_stargazing_plan


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


def test_analysis_area_serializes_popularity_fields():
    """Popularity heuristic fields should survive analysis_area serialization."""

    class MockCache:
        def __init__(self):
            self.store = {}

        def get(self, key):
            return self.store.get(key)

        def set(self, key, value):
            self.store[key] = value

    async def run_test():
        with (
            patch('src.functions.places.impl.StargazingPlaceFinder') as MockPF,
            patch('src.functions.places.impl.ANALYSIS_CACHE', new=MockCache()),
        ):
            mock_instance = MockPF.return_value
            mock_instance.analyze_area.return_value = [
                {
                    'name': 'Quiet Ridge',
                    'lat': 35.0,
                    'lon': -120.0,
                    'stargazing_score': 81.0,
                    'static_popularity_risk_score': 24.0,
                    'night_quiet_likelihood_score': 72.0,
                    'temporal_popularity_confidence': 61.0,
                    'nearby_popular_poi_count': 1,
                    'nearby_night_active_poi_count': 0,
                    'nearby_day_only_poi_count': 1,
                    'popularity_signals': ['距道路较远，夜间停留门槛更高'],
                    'temporal_popularity_signals': ['远离城镇，夜间退潮概率更高'],
                    'popularity_notes': '热门风险较低; 夜间大概率退潮',
                }
            ]

            result = await analysis_area.fn(
                south=30, west=100, north=31, east=101, page=1, page_size=10
            )

            item = result['data']['items'][0]
            assert item['static_popularity_risk_score'] == 24.0
            assert item['night_quiet_likelihood_score'] == 72.0
            assert item['temporal_popularity_confidence'] == 61.0
            assert item['nearby_popular_poi_count'] == 1
            assert item['nearby_night_active_poi_count'] == 0
            assert item['nearby_day_only_poi_count'] == 1
            assert item['popularity_notes'] == '热门风险较低; 夜间大概率退潮'

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
async def test_analysis_area_resource_id_changes_with_popularity_preferences():
    """Popularity preference parameters should participate in the resource identifier."""

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
            avoid_popular_spots=False,
            prefer_quiet_at_night=False,
            popularity_radius_km=3.0,
        )
        result_b = await analysis_area.fn(
            south=30.0,
            west=100.0,
            north=31.0,
            east=101.0,
            avoid_popular_spots=True,
            prefer_quiet_at_night=True,
            popularity_radius_km=4.0,
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
        ('popularity_radius_km', 0, 'popularity_radius_km must be greater than 0.'),
    ],
)
async def test_analysis_area_rejects_invalid_pagination_inputs(
    field_name: str,
    field_value: int | float,
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


@pytest.mark.asyncio
async def test_get_best_stargazing_plan_rejects_invalid_candidate_limit():
    """Invalid planning limits should return the standard structured error payload."""
    result = await get_best_stargazing_plan.fn(
        south=30.0,
        west=100.0,
        north=31.0,
        east=101.0,
        time='2024-06-15 20:00:00',
        time_zone='UTC',
        candidate_limit=0,
    )

    assert result['_meta']['status'] == 'error'
    assert result['error']['code'] == 'CONFIGURATION_ERROR'
    assert result['error']['message'] == 'candidate_limit must be greater than or equal to 1.'
    assert result['error']['details'] == {'candidate_limit': 0}


@pytest.mark.asyncio
async def test_get_best_stargazing_plan_rejects_invalid_bounds():
    """Invalid bounding boxes should return the standard structured error payload."""
    result = await get_best_stargazing_plan.fn(
        south=31.0,
        west=100.0,
        north=30.0,
        east=101.0,
        time='2024-06-15 20:00:00',
        time_zone='UTC',
    )

    assert result['_meta']['status'] == 'error'
    assert result['error']['code'] == 'CONFIGURATION_ERROR'
    assert result['error']['message'] == 'south must be less than north.'
    assert result['error']['details'] == {'south': 31.0, 'north': 30.0}


class TestResponseReservedFields:
    """Tests for reserved _meta fields for future long-task / streaming support."""

    def test_format_response_without_reserved_fields(self):
        """Legacy behavior: format_response without progress/task_id keeps minimal _meta."""
        from src.response import format_response

        result = format_response({'key': 'value'})
        assert result['_meta'] == {'version': '1.0.0', 'status': 'success'}

    def test_format_response_with_progress(self):
        """format_response with progress adds the field to _meta."""
        from src.response import format_response

        result = format_response({'key': 'value'}, progress=0.5)
        assert result['_meta']['progress'] == 0.5
        assert result['_meta']['status'] == 'success'

    def test_format_response_with_task_id(self):
        """format_response with task_id adds the field to _meta."""
        from src.response import format_response

        result = format_response({'key': 'value'}, task_id='task-abc-123')
        assert result['_meta']['task_id'] == 'task-abc-123'
        assert result['_meta']['status'] == 'success'

    def test_format_response_with_both_reserved_fields(self):
        """format_response with both progress and task_id adds both to _meta."""
        from src.response import format_response

        result = format_response({'key': 'value'}, progress=0.75, task_id='task-xyz')
        assert result['_meta']['progress'] == 0.75
        assert result['_meta']['task_id'] == 'task-xyz'
        assert result['_meta']['status'] == 'success'
        assert result['_meta']['version'] == '1.0.0'

    def test_format_response_reserved_fields_combine_with_custom_meta(self):
        """Reserved fields don't conflict with custom meta passed via the meta kwarg."""
        from src.response import format_response

        result = format_response(
            {'key': 'value'},
            meta={'custom': 'field'},
            progress=0.3,
            task_id='t-1',
        )
        assert result['_meta']['progress'] == 0.3
        assert result['_meta']['task_id'] == 't-1'
        assert result['_meta']['custom'] == 'field'

    def test_format_error_without_task_id(self):
        """Legacy behavior: format_error without task_id keeps minimal _meta."""
        from src.response import format_error

        result = format_error('TEST_ERR', 'something went wrong')
        assert result['_meta'] == {'version': '1.0.0', 'status': 'error'}
        assert 'task_id' not in result['_meta']

    def test_format_error_with_task_id(self):
        """format_error with task_id adds the field to _meta."""
        from src.response import format_error

        result = format_error('TEST_ERR', 'something went wrong', task_id='task-err')
        assert result['_meta']['task_id'] == 'task-err'
        assert result['_meta']['status'] == 'error'
        assert result['error']['code'] == 'TEST_ERR'
