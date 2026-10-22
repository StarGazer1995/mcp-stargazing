import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[1] / '.github' / 'scripts' / 'release_guard.py'


def load_release_guard_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location('release_guard', SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


release_guard = load_release_guard_module()


def test_read_project_version(tmp_path: Path):
    pyproject = tmp_path / 'pyproject.toml'
    pyproject.write_text('[project]\nname = "demo"\nversion = "1.2.3"\n', encoding='utf-8')

    assert release_guard.read_project_version(pyproject) == '1.2.3'


def test_validate_tag_accepts_matching_version():
    release_guard.validate_tag('v1.2.3', '1.2.3')


def test_validate_tag_rejects_mismatch():
    with pytest.raises(ValueError, match='expected v1.2.3, got v1.2.4'):
        release_guard.validate_tag('v1.2.4', '1.2.3')


def test_validate_distribution_versions_accepts_wheel_and_sdist(tmp_path: Path):
    (tmp_path / 'mcp_stargazing-1.2.3-py3-none-any.whl').touch()
    (tmp_path / 'mcp_stargazing-1.2.3.tar.gz').touch()

    release_guard.validate_distribution_versions(tmp_path, '1.2.3')


def test_validate_distribution_versions_rejects_mismatch(tmp_path: Path):
    (tmp_path / 'mcp_stargazing-1.2.3-py3-none-any.whl').touch()
    (tmp_path / 'mcp_stargazing-1.2.4.tar.gz').touch()

    with pytest.raises(ValueError, match='Distribution version mismatch'):
        release_guard.validate_distribution_versions(tmp_path, '1.2.3')
