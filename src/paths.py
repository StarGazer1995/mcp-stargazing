from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = PROJECT_ROOT / 'src'
MODELS_DIR = SRC_ROOT / 'models'
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
