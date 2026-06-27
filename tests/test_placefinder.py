import importlib
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import src.placefinder as placefinder_module
from src.placefinder import StargazingPlaceFinder, get_light_pollution_grid


def _make_mock_location(name, latitude, longitude, stargazing_score):
    """Create a mock location object with the expected attributes."""
    loc = MagicMock()
    loc.name = name
    loc.latitude = latitude
    loc.longitude = longitude
    loc.stargazing_score = stargazing_score
    return loc


def _make_fake_spf(mock_analyzer):
    """Build a fake dependency module with the bridge entrypoints."""
    init_mock = MagicMock(return_value=mock_analyzer)
    grid_mock = MagicMock(return_value={'data': []})
    return SimpleNamespace(
        init_stargazing_analyzer=init_mock,
        get_light_pollution_grid=grid_mock,
    )


def test_init_uses_dependency_analyzer_factory():
    """Bridge initialization should create and keep the dependency analyzer."""
    mock_analyzer = MagicMock()
    fake_spf = _make_fake_spf(mock_analyzer)

    with patch.object(placefinder_module, '_load_spf', return_value=fake_spf):
        pf = StargazingPlaceFinder()

    assert pf.stargazing_analyzer is mock_analyzer
    fake_spf.init_stargazing_analyzer.assert_called_once_with(
        geotiff_path=None,
        min_height_difference=100.0,
        road_search_radius_km=10.0,
        db_config_path=None,
    )


def test_analyze_area_returns_dependency_results_and_expected_args():
    """Bridge calls should forward the normalized arguments to the dependency."""
    mock_loc = _make_mock_location(
        name='Top Stargazing Spot',
        latitude=40.001,
        longitude=116.199,
        stargazing_score=92.5,
    )
    mock_analyzer = MagicMock()
    mock_analyzer.analyze_area.return_value = [mock_loc]
    fake_spf = _make_fake_spf(mock_analyzer)

    with patch.object(placefinder_module, '_load_spf', return_value=fake_spf):
        pf = StargazingPlaceFinder()
        result = pf.analyze_area(
            39.98,
            116.18,
            40.02,
            116.22,
            max_locations=3,
            min_height_diff=50.0,
            road_radius_km=5.0,
            network_type='drive',
        )

    assert result == [mock_loc]
    mock_analyzer.analyze_area.assert_called_once_with(
        bbox=(39.98, 116.18, 40.02, 116.22),
        max_locations=3,
        location_types=None,
        network_type='drive',
        include_light_pollution=True,
        include_road_connectivity=True,
    )


def test_analyze_area_reinitializes_only_when_thresholds_change():
    """Analyzer reuse should depend only on the bridge's threshold parameters."""
    mock_analyzer = MagicMock()
    mock_analyzer.analyze_area.return_value = []
    fake_spf = _make_fake_spf(mock_analyzer)

    with patch.object(placefinder_module, '_load_spf', return_value=fake_spf):
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

    assert pf.min_height_difference == 150.0
    assert pf.road_search_radius_km == 3.0
    assert fake_spf.init_stargazing_analyzer.call_count == 2


def test_init_with_db_config_path_forwards_path():
    """Bridge initialization should preserve the caller's database config path."""
    mock_analyzer = MagicMock()
    fake_spf = _make_fake_spf(mock_analyzer)
    db_config_path = Path('/tmp/db_config.json')

    with patch.object(placefinder_module, '_load_spf', return_value=fake_spf):
        pf = StargazingPlaceFinder(db_config_path=db_config_path)

    assert pf.db_config_path == db_config_path
    fake_spf.init_stargazing_analyzer.assert_called_once_with(
        geotiff_path=None,
        min_height_difference=100.0,
        road_search_radius_km=10.0,
        db_config_path=db_config_path,
    )


def test_prepare_spf_import_path_returns_none_when_dependency_root_unknown():
    """No path mutation should happen when the dependency source root cannot be found."""
    original_sys_path = list(sys.path)

    with patch.object(placefinder_module, 'resolve_package_source_root', return_value=None):
        assert placefinder_module._prepare_spf_import_path() is None
        assert sys.path == original_sys_path


def test_prepare_spf_import_path_prioritizes_dependency_root_and_clears_shadow_module():
    """The bridge should prefer the dependency source root over the local `src/models`."""
    fake_dependency_root = Path('/workspace/stargazing-place-finder/src')
    fake_repo_models = ModuleType('models')
    fake_repo_models.__file__ = '/app/src/models/__init__.py'
    original_sys_path = list(sys.path)
    original_models_module = sys.modules.get('models')
    fake_site_packages = '/usr/local/lib/python3.13/site-packages'

    try:
        sys.path = ['/app/src', str(fake_dependency_root), fake_site_packages]
        sys.modules['models'] = fake_repo_models
        with patch.object(placefinder_module, 'MODELS_DIR', Path('/app/src/models')):
            with patch.object(
                placefinder_module,
                'resolve_package_source_root',
                return_value=fake_dependency_root,
            ):
                with patch.object(
                    placefinder_module,
                    'find_module_origin',
                    return_value='/app/src/models/__init__.py',
                ):
                    with patch.object(
                        placefinder_module,
                        'is_repo_models_origin',
                        return_value=True,
                    ):
                        source_root = placefinder_module._prepare_spf_import_path()

        assert source_root == fake_dependency_root
        assert sys.path[0] == str(fake_dependency_root.resolve())
        assert 'models' not in sys.modules
    finally:
        sys.path = original_sys_path
        if original_models_module is None:
            sys.modules.pop('models', None)
        else:
            sys.modules['models'] = original_models_module


def test_prepare_spf_import_path_clears_loaded_repo_models_even_when_lookup_is_clean():
    """A shadowing cached module should be discarded when current lookup no longer sees it."""
    fake_dependency_root = Path('/workspace/stargazing-place-finder/src')
    fake_repo_models = ModuleType('models')
    fake_repo_models.__file__ = '/app/src/models/__init__.py'
    original_sys_path = list(sys.path)
    original_models_module = sys.modules.get('models')

    try:
        sys.path = ['/app/src', str(fake_dependency_root)]
        sys.modules['models'] = fake_repo_models
        with patch.object(placefinder_module, 'MODELS_DIR', Path('/app/src/models')):
            with patch.object(
                placefinder_module,
                'resolve_package_source_root',
                return_value=fake_dependency_root,
            ):
                with patch.object(placefinder_module, 'find_module_origin', return_value=None):
                    with patch.object(
                        placefinder_module,
                        'is_repo_models_origin',
                        side_effect=[False, True],
                    ):
                        source_root = placefinder_module._prepare_spf_import_path()

        assert source_root == fake_dependency_root
        assert sys.path[0] == str(fake_dependency_root.resolve())
        assert 'models' not in sys.modules
    finally:
        sys.path = original_sys_path
        if original_models_module is None:
            sys.modules.pop('models', None)
        else:
            sys.modules['models'] = original_models_module


def test_load_spf_wraps_missing_dependency_error():
    """A missing dependency should produce a clear bridge-level error."""
    missing_dependency = ModuleNotFoundError("No module named 'stargazingplacefinder'")
    missing_dependency.name = placefinder_module.SPF_PACKAGE_NAME

    with patch.object(placefinder_module, '_prepare_spf_import_path'):
        with patch.object(importlib, 'import_module', side_effect=missing_dependency):
            with pytest.raises(ModuleNotFoundError, match='stargazingplacefinder is required'):
                placefinder_module._load_spf()


def test_load_spf_reraises_unrelated_module_errors():
    """Nested dependency import errors should not be rewritten as missing package errors."""
    nested_failure = ModuleNotFoundError("No module named 'nested_module'")
    nested_failure.name = 'nested_module'

    with patch.object(placefinder_module, '_prepare_spf_import_path'):
        with patch.object(importlib, 'import_module', side_effect=nested_failure):
            with pytest.raises(ModuleNotFoundError, match='nested_module'):
                placefinder_module._load_spf()


def test_get_light_pollution_grid_uses_loaded_dependency_module():
    """The light pollution helper should proxy calls through the loaded dependency module."""
    fake_spf = _make_fake_spf(MagicMock())
    fake_spf.get_light_pollution_grid.return_value = {'data': ['grid-point']}

    with patch.object(placefinder_module, '_load_spf', return_value=fake_spf):
        result = get_light_pollution_grid(40.0, 39.0, 117.0, 116.0, zoom=9)

    assert result == {'data': ['grid-point']}
    fake_spf.get_light_pollution_grid.assert_called_once_with(
        north=40.0,
        south=39.0,
        east=117.0,
        west=116.0,
        zoom=9,
    )
