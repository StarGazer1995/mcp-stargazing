from src import paths


def test_resolve_repo_path_returns_project_relative_path():
    resolved = paths.resolve_repo_path('src', 'placefinder.py')

    assert resolved == (paths.PROJECT_ROOT / 'src' / 'placefinder.py').resolve()


def test_is_within_path_detects_nested_path():
    nested_path = paths.MODELS_DIR / '__init__.py'

    assert paths.is_within_path(nested_path, paths.MODELS_DIR) is True


def test_is_within_path_rejects_none_and_external_path():
    assert paths.is_within_path(None, paths.MODELS_DIR) is False
    assert paths.is_within_path('/tmp/external.py', paths.MODELS_DIR) is False


def test_path_constants_point_to_expected_locations():
    assert paths.SRC_ROOT == paths.PROJECT_ROOT / 'src'
    assert paths.MODELS_DIR == paths.SRC_ROOT / 'models'
    assert paths.DATA_DIR == paths.SRC_ROOT / 'data'
    assert paths.TESTS_DIR == paths.PROJECT_ROOT / 'tests'
    assert paths.EXAMPLES_DIR == paths.PROJECT_ROOT / 'examples'
    assert paths.SCRIPTS_DIR == paths.PROJECT_ROOT / 'scripts'
    assert (paths.PROJECT_ROOT / 'pyproject.toml').exists()
