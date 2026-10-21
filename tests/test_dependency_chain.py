import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[1] / '.github' / 'scripts' / 'dependency_chain.py'


def load_dependency_chain_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location('dependency_chain', SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dependency_chain = load_dependency_chain_module()


def write_result(
    results_dir: Path,
    mode: str,
    target: str,
    *,
    exit_code: int,
    failed_tests: list[str],
) -> None:
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / f'{mode}-{target}.json').write_text(
        json.dumps(
            {
                'mode': mode,
                'target': target,
                'exit_code': exit_code,
                'failed_tests': failed_tests,
            }
        ),
        encoding='utf-8',
    )


def test_redirect_lockfile_to_pypi_for_ci_retry(tmp_path: Path) -> None:
    lockfile = tmp_path / 'uv.lock'
    lockfile.write_text(
        '\n'.join(
            [
                'source = { registry = "https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple" }',
                'sdist = { url = "https://mirrors.tuna.tsinghua.edu.cn'
                '/pypi/web/packages/a/pkg.tar.gz" }',
                'wheels = [',
                '  { url = "https://mirrors.tuna.tsinghua.edu.cn/pypi/web/packages/b/pkg.whl" },',
                ']',
            ]
        ),
        encoding='utf-8',
    )

    assert dependency_chain.redirect_lockfile_to_pypi(lockfile) == 3
    rewritten = lockfile.read_text(encoding='utf-8')
    assert 'mirrors.tuna.tsinghua.edu.cn' not in rewritten
    assert 'https://pypi.org/simple' in rewritten
    assert 'https://files.pythonhosted.org/packages/a/pkg.tar.gz' in rewritten
    assert 'https://files.pythonhosted.org/packages/b/pkg.whl' in rewritten
    assert dependency_chain.redirect_lockfile_to_pypi(lockfile) == 0


def test_prepare_matrix_for_core_includes_both_consumers() -> None:
    matrix = dependency_chain.prepare_matrix(
        'StarGazer1995/stargazing-core',
        'candidate-sha',
        'baseline-sha',
        {'stargazing-place-finder': 'refs/pull/42/head'},
    )

    assert matrix == {
        'include': [
            {
                'mode': 'baseline',
                'target': 'spf',
                'changed_repo': 'core',
                'core_ref': 'baseline-sha',
                'spf_ref': 'refs/pull/42/head',
                'mcp_ref': 'main',
            },
            {
                'mode': 'baseline',
                'target': 'mcp',
                'changed_repo': 'core',
                'core_ref': 'baseline-sha',
                'spf_ref': 'refs/pull/42/head',
                'mcp_ref': 'main',
            },
            {
                'mode': 'candidate',
                'target': 'spf',
                'changed_repo': 'core',
                'core_ref': 'candidate-sha',
                'spf_ref': 'refs/pull/42/head',
                'mcp_ref': 'main',
            },
            {
                'mode': 'candidate',
                'target': 'mcp',
                'changed_repo': 'core',
                'core_ref': 'candidate-sha',
                'spf_ref': 'refs/pull/42/head',
                'mcp_ref': 'main',
            },
        ]
    }


def test_evaluate_allows_same_known_baseline_failure(tmp_path: Path) -> None:
    write_result(
        tmp_path,
        'baseline',
        'mcp',
        exit_code=1,
        failed_tests=['tests.test_place::test_existing_bug'],
    )
    write_result(
        tmp_path,
        'candidate',
        'mcp',
        exit_code=1,
        failed_tests=['tests.test_place::test_existing_bug'],
    )

    summary = tmp_path / 'summary.md'
    result = dependency_chain.evaluate_results('spf', tmp_path, summary)

    assert result == 0
    assert 'KNOWN_BASELINE' in summary.read_text(encoding='utf-8')


def test_evaluate_rejects_known_baseline_on_strict_gate(tmp_path: Path) -> None:
    write_result(
        tmp_path,
        'baseline',
        'mcp',
        exit_code=1,
        failed_tests=['tests.test_place::test_existing_bug'],
    )
    write_result(
        tmp_path,
        'candidate',
        'mcp',
        exit_code=1,
        failed_tests=['tests.test_place::test_existing_bug'],
    )

    summary = tmp_path / 'summary.md'
    result = dependency_chain.evaluate_results(
        'spf',
        tmp_path,
        summary,
        allow_known_baseline=False,
    )

    assert result == 1
    assert 'blocks the non-PR gate' in summary.read_text(encoding='utf-8')


def test_evaluate_blocks_new_candidate_failure(tmp_path: Path) -> None:
    write_result(
        tmp_path,
        'baseline',
        'mcp',
        exit_code=0,
        failed_tests=[],
    )
    write_result(
        tmp_path,
        'candidate',
        'mcp',
        exit_code=1,
        failed_tests=['tests.test_place::test_regression'],
    )

    summary = tmp_path / 'summary.md'
    result = dependency_chain.evaluate_results('spf', tmp_path, summary)

    assert result == 1
    assert 'introduces failures' in summary.read_text(encoding='utf-8')


@pytest.mark.parametrize(
    ('baseline_tests', 'candidate_tests'),
    [
        (['suite:unclassified'], ['suite:unclassified']),
        ([], ['suite:unclassified']),
    ],
)
def test_evaluate_rejects_uncomparable_baseline_failures(
    tmp_path: Path,
    baseline_tests: list[str],
    candidate_tests: list[str],
) -> None:
    write_result(
        tmp_path,
        'baseline',
        'mcp',
        exit_code=1,
        failed_tests=baseline_tests,
    )
    write_result(
        tmp_path,
        'candidate',
        'mcp',
        exit_code=1,
        failed_tests=candidate_tests,
    )

    summary = tmp_path / 'summary.md'
    result = dependency_chain.evaluate_results('spf', tmp_path, summary)

    assert result == 1
    assert 'without comparable test IDs' in summary.read_text(encoding='utf-8')
