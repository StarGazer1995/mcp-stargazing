import importlib
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import src.placefinder as placefinder_module
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
            self.assertEqual(mock_init.call_count, 3)

    def test_analyze_area_reuses_existing_analyzer_when_params_unchanged(self):
        """相同空间参数下不应重复初始化 analyzer。"""
        with patch('stargazingplacefinder.init_stargazing_analyzer') as mock_init:
            mock_analyzer = MagicMock()
            mock_analyzer.analyze_area.return_value = []
            mock_init.return_value = mock_analyzer

            pf = StargazingPlaceFinder(min_height_difference=50.0, road_search_radius_km=5.0)
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

            self.assertEqual(mock_init.call_count, 1)

    def test_reload_placefinder_ignores_find_spec_errors(self):
        """模块初始化时，find_spec 异常应被安全忽略。"""
        original_find_spec = importlib.util.find_spec
        original_sys_path = list(sys.path)

        def _raise_import_error(name):
            raise ImportError(f'boom: {name}')

        try:
            importlib.util.find_spec = _raise_import_error
            reloaded = importlib.reload(placefinder_module)
            self.assertIsNotNone(reloaded)
            self.assertEqual(sys.path, original_sys_path)
        finally:
            importlib.util.find_spec = original_find_spec
            importlib.reload(placefinder_module)

    def test_is_repo_models_origin_matches_ci_style_path(self):
        """Path 比对应兼容 CI 中的 `/app/src/models` 路径。"""
        original_models_dir = placefinder_module.MODELS_DIR

        try:
            placefinder_module.MODELS_DIR = Path('/app/src/models')
            self.assertTrue(
                placefinder_module._is_repo_models_origin('/app/src/models/__init__.py')
            )
            self.assertFalse(
                placefinder_module._is_repo_models_origin(
                    '/usr/local/lib/python3.13/site-packages/models/__init__.py'
                )
            )
        finally:
            placefinder_module.MODELS_DIR = original_models_dir

    def test_reload_placefinder_prioritizes_site_packages_for_repo_models_path(self):
        """当 models 解析到仓库内 `src/models` 时，应将 site-packages 提前。"""
        original_find_spec = importlib.util.find_spec
        original_sys_path = list(sys.path)

        fake_site_packages = '/usr/local/lib/python3.13/site-packages'
        fake_repo_src = str(Path(placefinder_module.__file__).resolve().parent)
        fake_repo_models = str(Path(fake_repo_src) / 'models' / '__init__.py')

        def _fake_find_spec(name):
            if name == 'models':
                return SimpleNamespace(origin=fake_repo_models)
            return original_find_spec(name)

        try:
            importlib.util.find_spec = _fake_find_spec
            sys.path = [fake_repo_src, fake_site_packages]
            reloaded = importlib.reload(placefinder_module)
            self.assertIsNotNone(reloaded)
            self.assertEqual(sys.path[0], fake_site_packages)
            self.assertEqual(sys.path[1], fake_repo_src)
        finally:
            importlib.util.find_spec = original_find_spec
            sys.path = original_sys_path
            importlib.reload(placefinder_module)

    def test_init_with_db_config(self):
        """验证支持 db_config_path 参数初始化"""
        from pathlib import Path

        pf = StargazingPlaceFinder(db_config_path=Path('/tmp/db_config.json'))
        self.assertEqual(pf.db_config_path, Path('/tmp/db_config.json'))
        self.assertIsNotNone(pf.stargazing_analyzer)
