import unittest
from src.placefinder import StargazingPlaceFinder


class TestStargazingPlaceFinder(unittest.TestCase):
    def test_init(self):
        """验证初始化成功并持有分析器实例"""
        pf = StargazingPlaceFinder()
        self.assertIsNotNone(pf.stargazing_analyzer)

    def test_analyze_area_objects(self):
        """调用 analyze_area 返回对象列表并包含关键属性"""
        pf = StargazingPlaceFinder()
        res = pf.analyze_area(
            39.98, 116.18, 40.02, 116.22,
            max_locations=3,
            min_height_diff=50.0,
            road_radius_km=5.0,
            network_type='drive'
        )
        self.assertIsInstance(res, list)
        if len(res) > 0:
            first = res[0]
            self.assertTrue(hasattr(first, 'name'))
            self.assertTrue(hasattr(first, 'latitude'))
            self.assertTrue(hasattr(first, 'stargazing_score'))

    def test_parameter_update(self):
        """analyze_area 应更新实例中的参数状态"""
        pf = StargazingPlaceFinder()
        pf.analyze_area(
            39.98, 116.18, 40.02, 116.22,
            max_locations=1,
            min_height_diff=50.0,
            road_radius_km=5.0,
            network_type='drive'
        )
        self.assertEqual(pf.min_height_difference, 50.0)
        self.assertEqual(pf.road_search_radius_km, 5.0)

        pf.analyze_area(
            39.98, 116.18, 40.02, 116.22,
            max_locations=1,
            min_height_diff=150.0,
            road_radius_km=3.0,
            network_type='drive'
        )
        self.assertEqual(pf.min_height_difference, 150.0)
        self.assertEqual(pf.road_search_radius_km, 3.0)

    def test_init_with_db_config(self):
        """验证支持 db_config_path 参数初始化"""
        from pathlib import Path
        pf = StargazingPlaceFinder(db_config_path=Path("/tmp/db_config.json"))
        self.assertEqual(pf.db_config_path, Path("/tmp/db_config.json"))
        self.assertIsNotNone(pf.stargazing_analyzer)