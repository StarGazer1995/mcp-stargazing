"""Contracts that keep agent-facing documentation aligned with the code."""

import re
from pathlib import Path

import src.main  # noqa: F401
from src.schemas.error import ErrorCode
from src.server_instance import mcp

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_readme_lists_every_registered_tool():
    readme = (PROJECT_ROOT / 'README.md').read_text(encoding='utf-8')
    registered = {tool['name'] for tool in mcp.get_tool_catalog()}

    missing = {name for name in registered if f'`{name}`' not in readme}
    assert not missing, f'Registered tools missing from README: {sorted(missing)}'


def test_readme_example_paths_exist():
    readme = (PROJECT_ROOT / 'README.md').read_text(encoding='utf-8')
    referenced = set(re.findall(r'python (examples/[A-Za-z0-9_./-]+\.py)', readme))
    missing = {path for path in referenced if not (PROJECT_ROOT / path).is_file()}

    assert not missing, f'README references missing examples: {sorted(missing)}'


def test_agents_error_codes_match_contract_enum():
    agents = (PROJECT_ROOT / 'AGENTS.md').read_text(encoding='utf-8')
    missing = {code.value for code in ErrorCode if code.value not in agents}

    assert not missing, f'AGENTS.md is missing error codes: {sorted(missing)}'
