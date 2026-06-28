import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import ANY, MagicMock, patch

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


def _make_fake_spf(mock_analyzer=None):
    """Build a fake dependency module with the bridge entrypoints."""
    if mock_analyzer is None:
        mock_analyzer = MagicMock()
    init_mock = MagicMock(return_value=None)
    grid_mock = MagicMock(return_value={'data': []})
    return SimpleNamespace(
        init_stargazing_analyzer=init_mock,
        get_light_pollution_grid=grid_mock,
    )


# ── StargazingPlaceFinder ────────────────────────────────────────────────────


def test_init_uses_dependency_analyzer_factory():
    """Bridge initialization should configure the SPF singleton via the public API."""
    placefinder_module._last_params = None  # isolate from other tests
    mock_analyzer = MagicMock()
    fake_spf = _make_fake_spf(mock_analyzer)

    with patch.object(placefinder_module, '_load_spf', return_value=fake_spf):
        StargazingPlaceFinder()

    fake_spf.init_stargazing_analyzer.assert_called_once_with(
        geotiff_path=None,
        min_height_difference=100.0,
        road_search_radius_km=10.0,
        db_config_path=None,
        config=ANY,
    )


def test_init_analyzer_skipped_when_params_unchanged():
    """Repeated initialization with same params should NOT reconfigure SPF."""
    placefinder_module._last_params = None  # isolate from other tests
    mock_analyzer = MagicMock()
    fake_spf = _make_fake_spf(mock_analyzer)

    with patch.object(placefinder_module, '_load_spf', return_value=fake_spf):
        StargazingPlaceFinder(min_height_difference=100.0, road_search_radius_km=10.0)

    assert fake_spf.init_stargazing_analyzer.call_count == 1

    # Second instance with identical params — should NOT call init again
    with patch.object(placefinder_module, '_load_spf', return_value=fake_spf):
        StargazingPlaceFinder(min_height_difference=100.0, road_search_radius_km=10.0)

    assert fake_spf.init_stargazing_analyzer.call_count == 1  # still 1


def test_init_analyzer_called_when_params_change():
    """Different parameters should trigger reconfiguration."""
    placefinder_module._last_params = None  # isolate from other tests
    mock_analyzer = MagicMock()
    fake_spf = _make_fake_spf(mock_analyzer)

    with patch.object(placefinder_module, '_load_spf', return_value=fake_spf):
        StargazingPlaceFinder(min_height_difference=100.0, road_search_radius_km=10.0)

    assert fake_spf.init_stargazing_analyzer.call_count == 1

    # Different params — should call init again
    with patch.object(placefinder_module, '_load_spf', return_value=fake_spf):
        StargazingPlaceFinder(min_height_difference=200.0, road_search_radius_km=5.0)

    assert fake_spf.init_stargazing_analyzer.call_count == 2


def test_analyze_area_returns_dependency_results_and_expected_args():
    """Bridge calls should forward the normalized arguments to the dependency."""
    placefinder_module._last_params = None  # isolate from other tests
    mock_loc = _make_mock_location(
        name='Top Stargazing Spot',
        latitude=40.001,
        longitude=116.199,
        stargazing_score=92.5,
    )
    mock_analyzer = MagicMock()
    fake_spf = _make_fake_spf(mock_analyzer)
    fake_spf.analyze_area = MagicMock(return_value=[mock_loc])

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
    fake_spf.analyze_area.assert_called_once_with(
        bbox=(39.98, 116.18, 40.02, 116.22),
        max_locations=3,
        network_type='drive',
        include_light_pollution=True,
        include_road_connectivity=True,
    )


def test_analyze_area_reinitializes_only_when_thresholds_change():
    """Analyzer reuse should depend only on the bridge's threshold parameters."""
    fake_spf = _make_fake_spf()
    fake_spf.analyze_area = MagicMock(return_value=[])

    # Reset global state to isolate this test
    placefinder_module._last_params = None

    with patch.object(placefinder_module, '_load_spf', return_value=fake_spf):
        pf = StargazingPlaceFinder(min_height_difference=50.0, road_search_radius_km=5.0)
        assert fake_spf.init_stargazing_analyzer.call_count == 1

        pf.analyze_area(
            39.98,
            116.18,
            40.02,
            116.22,
            max_locations=1,
            min_height_diff=50.0,  # same as constructor
            road_radius_km=5.0,  # same as constructor
            network_type='drive',
        )
        # analyze_area should NOT re-init when params match self.*
        assert fake_spf.init_stargazing_analyzer.call_count == 1

        pf.analyze_area(
            39.98,
            116.18,
            40.02,
            116.22,
            max_locations=1,
            min_height_diff=150.0,  # changed
            road_radius_km=3.0,  # changed
            network_type='drive',
        )
        # analyze_area SHOULD re-init when params change
        assert fake_spf.init_stargazing_analyzer.call_count == 2

    assert pf.min_height_difference == 150.0
    assert pf.road_search_radius_km == 3.0


def test_init_with_db_config_path_forwards_path():
    """Bridge initialization should preserve the caller's database config path."""
    placefinder_module._last_params = None  # isolate from other tests
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
        config=ANY,
    )


# ── _prepare_spf_import_path (simplified — no longer handles models shadowing) ─


def test_prepare_spf_import_path_returns_none_when_dependency_root_unknown():
    """No path mutation should happen when the dependency source root cannot be found."""
    original_sys_path = list(sys.path)

    with patch.object(placefinder_module, 'resolve_package_source_root', return_value=None):
        assert placefinder_module._prepare_spf_import_path() is None
        assert sys.path == original_sys_path


def test_prepare_spf_import_path_prioritizes_dependency_root():
    """The bridge should move the SPF source root to the front of sys.path."""
    fake_dependency_root = Path('/workspace/stargazing-place-finder/src')
    original_sys_path = list(sys.path)

    try:
        sys.path = ['/app/src', str(fake_dependency_root), '/tmp/other']
        with patch.object(
            placefinder_module,
            'resolve_package_source_root',
            return_value=fake_dependency_root,
        ):
            source_root = placefinder_module._prepare_spf_import_path()

        assert source_root == fake_dependency_root
        assert sys.path[0] == str(fake_dependency_root.resolve())
    finally:
        sys.path = original_sys_path


# ── _load_spf ────────────────────────────────────────────────────────────────


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


# ── get_light_pollution_grid ─────────────────────────────────────────────────


def test_get_light_pollution_grid_uses_loaded_dependency_module():
    """The light pollution helper should proxy calls through the loaded dependency module."""
    fake_spf = _make_fake_spf()
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
