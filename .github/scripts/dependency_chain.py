#!/usr/bin/env python3
"""Prepare and evaluate cross-repository dependency-chain checks."""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

REPO_ALIASES = {
    'core': 'core',
    'stargazing-core': 'core',
    'spf': 'spf',
    'stargazing-place-finder': 'spf',
    'mcp': 'mcp',
    'mcp-stargazing': 'mcp',
}

TARGETS_BY_CHANGED_REPO = {
    'core': ('spf', 'mcp'),
    'spf': ('mcp',),
    'mcp': ('mcp',),
}

DEFAULT_REFS = {
    'core': 'main',
    'spf': 'main',
    'mcp': 'main',
}


def bool_from_string(value: str) -> bool:
    """Parse a conservative boolean value from a CLI argument."""
    normalized = value.strip().lower()
    if normalized in {'true', '1', 'yes'}:
        return True
    if normalized in {'false', '0', 'no'}:
        return False
    raise argparse.ArgumentTypeError(f'Expected a boolean value, got {value!r}')


def normalize_repo(value: str) -> str:
    """Normalize a repository name or owner/repository value."""
    repo_name = value.rstrip('/').rsplit('/', 1)[-1]
    if repo_name.endswith('.git'):
        repo_name = repo_name[:-4]

    try:
        return REPO_ALIASES[repo_name]
    except KeyError as exc:
        valid = ', '.join(sorted(REPO_ALIASES))
        raise ValueError(f'Unknown repository {value!r}. Expected one of: {valid}') from exc


def write_github_output(path: Path, name: str, value: str) -> None:
    """Write a multiline-safe GitHub Actions output."""
    delimiter = f'__DEPENDENCY_CHAIN_{name.upper()}__'
    with path.open('a', encoding='utf-8') as output:
        output.write(f'{name}<<{delimiter}\n{value}\n{delimiter}\n')


def prepare_matrix(
    changed_repository: str,
    candidate_ref: str,
    baseline_ref: str,
    overrides: dict[str, str],
) -> dict[str, list[dict[str, str]]]:
    """Build baseline/candidate jobs for every affected downstream repository."""
    changed = normalize_repo(changed_repository)
    refs = dict(DEFAULT_REFS)

    for repository, ref in overrides.items():
        normalized = normalize_repo(repository)
        if not isinstance(ref, str) or not ref.strip():
            raise ValueError(f'Invalid ref override for {repository!r}')
        refs[normalized] = ref.strip()

    includes: list[dict[str, str]] = []
    for mode, changed_ref in (
        ('baseline', baseline_ref),
        ('candidate', candidate_ref),
    ):
        mode_refs = dict(refs)
        mode_refs[changed] = changed_ref
        for target in TARGETS_BY_CHANGED_REPO[changed]:
            includes.append(
                {
                    'mode': mode,
                    'target': target,
                    'changed_repo': changed,
                    'core_ref': mode_refs['core'],
                    'spf_ref': mode_refs['spf'],
                    'mcp_ref': mode_refs['mcp'],
                }
            )

    return {'include': includes}


def failed_tests_from_junit(path: Path) -> list[str]:
    """Return stable identifiers for failed or errored JUnit test cases."""
    if not path.is_file():
        return []

    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return ['junit:parse-error']

    failures: set[str] = set()
    for testcase in root.iter('testcase'):
        failure_nodes = [child for child in testcase if child.tag in {'failure', 'error'}]
        if not failure_nodes:
            continue

        classname = testcase.attrib.get('classname', '<unknown-class>')
        name = testcase.attrib.get('name', '<unknown-test>')
        failures.add(f'{classname}::{name}')

    return sorted(failures)


def read_evidence_tail(path: Path, limit: int = 5000) -> str:
    """Read the end of a test log for actionable CI evidence."""
    if not path.is_file():
        return ''
    try:
        return path.read_text(encoding='utf-8', errors='replace')[-limit:]
    except OSError as exc:
        return f'Unable to read test log: {exc}'


def summarize_result(args: argparse.Namespace) -> None:
    """Create a machine-readable result for one matrix job."""
    exit_code = int(args.exit_code_file.read_text(encoding='utf-8').strip())
    failed_tests = failed_tests_from_junit(args.junit)
    if exit_code != 0 and not failed_tests:
        failed_tests = ['suite:unclassified']

    result: dict[str, Any] = {
        'mode': args.mode,
        'target': args.target,
        'exit_code': exit_code,
        'failed_tests': failed_tests,
        'snapshot': {
            'core': args.core_ref,
            'spf': args.spf_ref,
            'mcp': args.mcp_ref,
        },
    }
    if exit_code != 0:
        result['evidence_tail'] = read_evidence_tail(args.log)

    args.result.parent.mkdir(parents=True, exist_ok=True)
    args.result.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
        encoding='utf-8',
    )


def load_results(results_dir: Path) -> dict[tuple[str, str], dict[str, Any]]:
    """Load matrix results keyed by mode and target."""
    results: dict[tuple[str, str], dict[str, Any]] = {}
    for path in sorted(results_dir.glob('*.json')):
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            key = (str(data['mode']), str(data['target']))
        except (KeyError, OSError, TypeError, ValueError) as exc:
            raise ValueError(f'Invalid dependency-chain result {path}: {exc}') from exc
        if key in results:
            raise ValueError(f'Duplicate matrix result for {key[0]}/{key[1]}')
        results[key] = data
    return results


def evaluate_results(
    changed_repository: str,
    results_dir: Path,
    summary_path: Path,
    *,
    allow_known_baseline: bool = True,
) -> int:
    """Fail only when the candidate adds failures relative to the baseline."""
    changed = normalize_repo(changed_repository)
    results = load_results(results_dir)
    targets = TARGETS_BY_CHANGED_REPO[changed]
    rows: list[tuple[str, str, str, str, str]] = []
    failed = False

    for target in targets:
        baseline = results.get(('baseline', target))
        candidate = results.get(('candidate', target))
        if baseline is None or candidate is None:
            rows.append((target, 'ERROR', 'ERROR', 'ERROR', 'Missing baseline or candidate result'))
            failed = True
            continue

        baseline_failures = set(baseline.get('failed_tests', []))
        candidate_failures = set(candidate.get('failed_tests', []))

        if candidate.get('exit_code') == 0:
            if baseline.get('exit_code') == 0:
                decision = 'PASS'
                note = 'Baseline and candidate both pass'
            else:
                decision = 'PASS'
                note = 'Candidate resolves baseline failures'
        elif baseline.get('exit_code') == 0:
            decision = 'FAIL'
            note = 'Candidate introduces failures'
            failed = True
        else:
            new_failures = candidate_failures - baseline_failures
            uncomparable = (
                not baseline_failures
                or baseline_failures == {'suite:unclassified'}
                or not candidate_failures
                or candidate_failures == {'suite:unclassified'}
            )
            if uncomparable:
                decision = 'FAIL'
                note = 'Both sides fail without comparable test IDs; fix the baseline'
                failed = True
            elif new_failures:
                decision = 'FAIL'
                note = 'Candidate adds failures: ' + ', '.join(sorted(new_failures))
                failed = True
            elif not allow_known_baseline:
                decision = 'FAIL'
                note = 'Known baseline failure blocks the non-PR gate'
                failed = True
            else:
                decision = 'KNOWN_BASELINE'
                note = 'Candidate adds no failures beyond the baseline'

        baseline_status = 'PASS' if baseline.get('exit_code') == 0 else 'FAIL'
        candidate_status = 'PASS' if candidate.get('exit_code') == 0 else 'FAIL'
        rows.append((target, baseline_status, candidate_status, decision, note))

    lines = [
        '## Dependency-chain result',
        '',
        f'Changed repository: `{changed}`',
        '',
        '| Target | Baseline | Candidate | Decision | Note |',
        '|---|---:|---:|---|---|',
    ]
    for target, baseline_status, candidate_status, decision, note in rows:
        lines.append(
            f'| `{target}` | {baseline_status} | {candidate_status} | {decision} | {note} |'
        )
    lines.extend(
        [
            '',
            'A `KNOWN_BASELINE` result does not fail this PR gate, but the same failure '
            'still blocks a healthy release candidate.',
            '',
        ]
    )

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text('\n'.join(lines), encoding='utf-8')
    return 1 if failed else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest='command', required=True)

    prepare = subparsers.add_parser('prepare')
    prepare.add_argument('--changed-repository', required=True)
    prepare.add_argument('--candidate-ref', required=True)
    prepare.add_argument('--baseline-ref', required=True)
    prepare.add_argument('--refs-json', default='{}')
    prepare.add_argument('--github-output', type=Path, required=True)

    summarize = subparsers.add_parser('summarize')
    summarize.add_argument('--mode', required=True)
    summarize.add_argument('--target', required=True)
    summarize.add_argument('--exit-code-file', type=Path, required=True)
    summarize.add_argument('--junit', type=Path, required=True)
    summarize.add_argument('--log', type=Path, required=True)
    summarize.add_argument('--result', type=Path, required=True)
    summarize.add_argument('--core-ref', required=True)
    summarize.add_argument('--spf-ref', required=True)
    summarize.add_argument('--mcp-ref', required=True)

    evaluate = subparsers.add_parser('evaluate')
    evaluate.add_argument('--changed-repository', required=True)
    evaluate.add_argument('--results-dir', type=Path, required=True)
    evaluate.add_argument('--summary-path', type=Path, required=True)
    evaluate.add_argument('--allow-known-baseline', required=True, type=bool_from_string)

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == 'prepare':
            overrides = json.loads(args.refs_json)
            if not isinstance(overrides, dict):
                raise ValueError('--refs-json must decode to a JSON object')
            matrix = prepare_matrix(
                args.changed_repository,
                args.candidate_ref,
                args.baseline_ref,
                overrides,
            )
            write_github_output(
                args.github_output,
                'matrix',
                json.dumps(matrix, separators=(',', ':')),
            )
        elif args.command == 'summarize':
            summarize_result(args)
        else:
            return evaluate_results(
                args.changed_repository,
                args.results_dir,
                args.summary_path,
                allow_known_baseline=args.allow_known_baseline,
            )
    except (OSError, ValueError) as exc:
        print(f'dependency-chain error: {exc}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
