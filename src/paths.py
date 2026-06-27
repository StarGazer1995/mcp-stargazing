import importlib
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = PROJECT_ROOT / 'src'
SCHEMAS_DIR = SRC_ROOT / 'schemas'
DATA_DIR = SRC_ROOT / 'data'
TESTS_DIR = PROJECT_ROOT / 'tests'
EXAMPLES_DIR = PROJECT_ROOT / 'examples'
SCRIPTS_DIR = PROJECT_ROOT / 'scripts'


def resolve_repo_path(*parts: str) -> Path:
    """Resolve a path relative to the repository root."""
    return PROJECT_ROOT.joinpath(*parts).resolve()


def is_within_path(path: str | Path | None, base_dir: Path) -> bool:
    """Return whether the resolved path is located under the given base directory."""
    if path is None:
        return False

    try:
        resolved_path = Path(path).resolve()
        resolved_path.relative_to(base_dir.resolve())
    except (OSError, RuntimeError, ValueError):
        return False

    return True


def is_repo_schemas_origin(origin: str | None) -> bool:
    """Return whether a module origin resolves under this repository's ``src/schemas``."""
    return is_within_path(origin, SCHEMAS_DIR)


def find_module_origin(module_name: str) -> str | None:
    """Return a module origin while safely ignoring lookup failures."""
    try:
        spec = importlib.util.find_spec(module_name)
    except (ImportError, ValueError, ModuleNotFoundError):
        return None

    if spec is None:
        return None

    return spec.origin


def resolve_package_source_root(package_name: str) -> Path | None:
    """Return the source root that should satisfy a package's top-level imports."""
    package_origin = find_module_origin(package_name)
    if package_origin is None:
        return None

    return Path(package_origin).resolve().parent.parent


def prioritize_sys_path(path: Path) -> None:
    """Move a path to the front of `sys.path` without leaving duplicates behind."""
    resolved_path = str(path.resolve())
    sys.path = [resolved_path, *[entry for entry in sys.path if entry != resolved_path]]


def discard_shadowing_module(module_name: str, base_dir: Path) -> None:
    """Remove a cached module when its loaded file resolves under the given directory."""
    loaded_module = sys.modules.get(module_name)
    if loaded_module is None:
        return

    loaded_origin = getattr(loaded_module, '__file__', None)
    if is_within_path(loaded_origin, base_dir):
        sys.modules.pop(module_name, None)
