import importlib
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from src import paths


def test_resolve_repo_path_returns_project_relative_path():
    resolved = paths.resolve_repo_path('src', 'placefinder.py')

    assert resolved == (paths.PROJECT_ROOT / 'src' / 'placefinder.py').resolve()


def test_is_within_path_detects_nested_path():
    nested_path = paths.SCHEMAS_DIR / '__init__.py'

    assert paths.is_within_path(nested_path, paths.SCHEMAS_DIR) is True


def test_is_within_path_rejects_none_and_external_path():
    assert paths.is_within_path(None, paths.SCHEMAS_DIR) is False
    assert paths.is_within_path('/tmp/external.py', paths.SCHEMAS_DIR) is False


def test_is_repo_schemas_origin_matches_ci_style_path():
    original_schemas_dir = paths.SCHEMAS_DIR

    try:
        paths.SCHEMAS_DIR = Path('/app/src/schemas')
        assert paths.is_repo_schemas_origin('/app/src/schemas/__init__.py') is True
        assert (
            paths.is_repo_schemas_origin(
                '/usr/local/lib/python3.13/site-packages/schemas/__init__.py'
            )
            is False
        )
    finally:
        paths.SCHEMAS_DIR = original_schemas_dir


def test_find_module_origin_returns_expected_origin():
    with patch.object(
        importlib.util,
        'find_spec',
        return_value=SimpleNamespace(origin='/tmp/pkg/__init__.py'),
    ):
        assert paths.find_module_origin('demo.module') == '/tmp/pkg/__init__.py'


def test_find_module_origin_returns_none_when_spec_missing():
    with patch.object(importlib.util, 'find_spec', return_value=None):
        assert paths.find_module_origin('demo.module') is None


def test_find_module_origin_ignores_lookup_errors():
    with patch.object(importlib.util, 'find_spec', side_effect=ImportError('boom')):
        assert paths.find_module_origin('demo.module') is None


def test_resolve_package_source_root_returns_none_when_origin_missing():
    with patch.object(paths, 'find_module_origin', return_value=None):
        assert paths.resolve_package_source_root('demo.module') is None


def test_resolve_package_source_root_returns_parent_src_directory():
    with patch.object(
        paths,
        'find_module_origin',
        return_value='/workspace/stargazing-place-finder/src/stargazingplacefinder/__init__.py',
    ):
        assert paths.resolve_package_source_root('stargazingplacefinder') == Path(
            '/workspace/stargazing-place-finder/src'
        )


def test_prioritize_sys_path_moves_entry_to_front_without_duplicates():
    original_sys_path = list(sys.path)
    target_path = Path('/workspace/stargazing-place-finder/src')

    try:
        sys.path = ['/app/src', str(target_path.resolve()), '/tmp/other']
        paths.prioritize_sys_path(target_path)
        assert sys.path[0] == str(target_path.resolve())
        assert sys.path.count(str(target_path.resolve())) == 1
    finally:
        sys.path = original_sys_path


def test_discard_shadowing_module_removes_module_under_base_dir():
    original_models_module = sys.modules.get('models')
    fake_models = ModuleType('models')
    fake_models.__file__ = '/app/src/schemas/__init__.py'

    try:
        sys.modules['models'] = fake_models
        paths.discard_shadowing_module('models', Path('/app/src/schemas'))
        assert 'models' not in sys.modules
    finally:
        if original_models_module is None:
            sys.modules.pop('models', None)
        else:
            sys.modules['models'] = original_models_module


def test_discard_shadowing_module_keeps_external_module():
    original_models_module = sys.modules.get('models')
    fake_models = ModuleType('models')
    fake_models.__file__ = '/usr/local/lib/python3.13/site-packages/models/__init__.py'

    try:
        sys.modules['models'] = fake_models
        paths.discard_shadowing_module('models', Path('/app/src/schemas'))
        assert sys.modules['models'] is fake_models
    finally:
        if original_models_module is None:
            sys.modules.pop('models', None)
        else:
            sys.modules['models'] = original_models_module


def test_path_constants_point_to_expected_locations():
    assert paths.SRC_ROOT == paths.PROJECT_ROOT / 'src'
    assert paths.SCHEMAS_DIR == paths.SRC_ROOT / 'schemas'
    assert paths.DATA_DIR == paths.SRC_ROOT / 'data'
    assert paths.TESTS_DIR == paths.PROJECT_ROOT / 'tests'
    assert paths.EXAMPLES_DIR == paths.PROJECT_ROOT / 'examples'
    assert paths.SCRIPTS_DIR == paths.PROJECT_ROOT / 'scripts'
    assert (paths.PROJECT_ROOT / 'pyproject.toml').exists()
