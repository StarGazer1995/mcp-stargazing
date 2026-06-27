import sys
from pathlib import Path


def ensure_project_root() -> Path:
    """Ensure the repository root is importable when examples run directly."""
    project_root = Path(__file__).resolve().parents[1]
    project_root_str = str(project_root)
    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)
    return project_root
