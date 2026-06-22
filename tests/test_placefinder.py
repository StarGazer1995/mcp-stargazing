import unittest
from unittest.mock import MagicMock, patch

from src.placefinder import StargazingPlaceFinder


def _make_mock_location(name, latitude, longitude, stargazing_score):
    """Create a mock location object with the expected attributes."""
    loc = MagicMock()
    loc.name = name
    loc.latitude = latitude
    loc.longitude = longitude
    loc.stargazing_score = stargazing_score
    return loc


class TestStargazingPlaceFinder(unittest.TestCase):
    def test_init(self):
        """验证初始化成功并持有分析器实例"""
        with patch('stargazingplacefinder.init_stargazing_analyzer') as mock_init:
            pf = StargazingPlaceFinder()
            self.assertIsNotNone(pf.stargazing_analyzer)
            mock_init.assert_called_once()

    def test_analyze_area_objects(self):
        """调用 analyze_area 返回对象列表并包含关键属性"""
        mock_loc = _make_mock_location(
            name='Top Stargazing Spot',
            latitude=40.001,
            longitude=116.199,
            stargazing_score=92.5,
        )

        with patch('stargazingplacefinder.init_stargazing_analyzer') as mock_init:
            mock_analyzer = MagicMock()
            mock_analyzer.analyze_area.return_value = [mock_loc]
            mock_init.return_value = mock_analyzer

            pf = StargazingPlaceFinder()
            res = pf.analyze_area(
                39.98,
                116.18,
                40.02,
                116.22,
                max_locations=3,
                min_height_diff=50.0,
                road_radius_km=5.0,
                network_type='drive',
            )
        self.assertIsInstance(res, list)
        self.assertEqual(len(res), 1)
        first = res[0]
        self.assertEqual(first.name, 'Top Stargazing Spot')
        self.assertEqual(first.latitude, 40.001)
        self.assertEqual(first.stargazing_score, 92.5)

    def test_parameter_update(self):
        """analyze_area 应更新实例中的参数状态"""
        with patch('stargazingplacefinder.init_stargazing_analyzer') as mock_init:
            mock_analyzer = MagicMock()
            mock_analyzer.analyze_area.return_value = []
            mock_init.return_value = mock_analyzer

            pf = StargazingPlaceFinder()
            pf.analyze_area(
                39.98,
                116.18,
                40.02,
                116.22,
                max_locations=1,
                min_height_diff=50.0,
                road_radius_km=5.0,
                network_type='drive',
            )
            self.assertEqual(pf.min_height_difference, 50.0)
            self.assertEqual(pf.road_search_radius_km, 5.0)

            pf.analyze_area(
                39.98,
                116.18,
                40.02,
                116.22,
                max_locations=1,
                min_height_diff=150.0,
                road_radius_km=3.0,
                network_type='drive',
            )
            self.assertEqual(pf.min_height_difference, 150.0)
            self.assertEqual(pf.road_search_radius_km, 3.0)

    def test_init_with_db_config(self):
        """验证支持 db_config_path 参数初始化"""
        from pathlib import Path

        pf = StargazingPlaceFinder(db_config_path=Path('/tmp/db_config.json'))
        self.assertEqual(pf.db_config_path, Path('/tmp/db_config.json'))
        self.assertIsNotNone(pf.stargazing_analyzer)
