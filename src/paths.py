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
