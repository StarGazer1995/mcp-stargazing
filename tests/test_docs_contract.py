"""Contracts that keep agent-facing documentation aligned with the code."""

import re
import tomllib
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


def test_local_markdown_doc_references_exist():
    source_text = '\n'.join(
        (PROJECT_ROOT / path).read_text(encoding='utf-8')
        for path in ('AGENTS.md', 'README.md', 'CLAUDE.md')
    )
    referenced = set(re.findall(r'(?:`|\()(docs/[A-Za-z0-9_./-]+\.md)(?:`|\))', source_text))
    missing = {path for path in referenced if not (PROJECT_ROOT / path).is_file()}

    assert not missing, f'Top-level docs reference missing documentation: {sorted(missing)}'


def test_readme_runtime_dependency_floors_match_pyproject():
    readme = (PROJECT_ROOT / 'README.md').read_text(encoding='utf-8')
    project = tomllib.loads((PROJECT_ROOT / 'pyproject.toml').read_text(encoding='utf-8'))
    dependencies = project['project']['dependencies']

    for package_name in ('stargazing-core', 'stargazing-place-finder'):
        dependency = next(item for item in dependencies if item.startswith(f'{package_name}>='))
        minimum_version = re.match(rf'{re.escape(package_name)}>=(\d+(?:\.\d+)*)', dependency)
        assert minimum_version is not None
        expected = f'{package_name}>={minimum_version.group(1)}'
        assert expected in readme, f'README must document the runtime dependency floor {expected}'


def test_planning_orchestration_does_not_chain_fastmcp_wrappers():
    """Application orchestration must use capabilities, never public tool ``.fn`` hooks."""
    sources = [
        PROJECT_ROOT / 'src/functions/planning/impl.py',
        PROJECT_ROOT / 'src/services/planning.py',
    ]
    offenders = [path for path in sources if '.fn(' in path.read_text(encoding='utf-8')]

    assert not offenders, f'Planning still chains FastMCP wrappers: {offenders}'
