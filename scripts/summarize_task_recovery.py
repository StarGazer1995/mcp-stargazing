"""Regrade preserved call evidence into a compact, reviewable client report."""

import argparse
import hashlib
import json
from pathlib import Path

from evaluations.task_recovery_golden import SCENARIOS
from scripts.run_task_recovery_clients import (
    extract_answer,
    read_events,
    score,
    used_only_evaluation_tools,
)
from src.paths import PROJECT_ROOT


def summarize(client, directory):
    results = []
    for scenario in SCENARIOS:
        case_dir = directory / scenario.key
        raw = read_events(case_dir / 'client.jsonl')
        calls = read_events(case_dir / 'calls.jsonl')
        original = json.loads((case_dir / 'result.json').read_text())
        answer = extract_answer(client, raw)
        result = score(scenario, answer, calls)
        result['client_tools_ok'] = used_only_evaluation_tools(client, raw)
        result['case'] = scenario.key
        result['passed'] = (
            original['exit_code'] == 0
            and not original['timed_out']
            and all(
                result[key]
                for key in (
                    'tool_selection',
                    'first_call_contract',
                    'trace_ok',
                    'exact_answer',
                    'client_tools_ok',
                )
            )
        )
        result['original_scoring_passed'] = original['passed']
        result['question'] = scenario.prompt
        result['calls'] = calls
        result['response_models'] = sorted(
            {
                item['message']['model']
                for item in raw
                if isinstance(item.get('message'), dict) and item['message'].get('model')
            }
        )
        invocation = case_dir / 'command.json'
        result['configured_model'] = None
        if invocation.exists():
            for argument in json.loads(invocation.read_text()):
                if argument.startswith('model='):
                    result['configured_model'] = json.loads(argument.removeprefix('model='))
        result['client_log_sha256'] = hashlib.sha256(
            (case_dir / 'client.jsonl').read_bytes()
        ).hexdigest()
        results.append(result)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--codex-dir', type=Path, required=True)
    parser.add_argument('--claude-dir', type=Path, required=True)
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--date', required=True, help='Report date, YYYY-MM-DD')
    args = parser.parse_args()
    results = {
        'codex': summarize('codex', args.codex_dir),
        'claude': summarize('claude', args.claude_dir),
    }
    metrics = {
        client: {
            key: sum(bool(row[key]) for row in rows)
            for key in (
                'tool_selection',
                'first_call_contract',
                'trace_ok',
                'exact_answer',
                'passed',
            )
        }
        | {'cases': len(rows)}
        for client, rows in results.items()
    }
    sources = [
        'evaluations/task_recovery_golden.py',
        'evaluations/task_recovery_golden.xml',
        'evaluations/task_recovery_server.py',
        'scripts/run_task_recovery_clients.py',
    ]
    report = {
        'date': args.date,
        'metrics': metrics,
        'results': results,
        'source_sha256': {
            path: hashlib.sha256((PROJECT_ROOT / path).read_bytes()).hexdigest() for path in sources
        },
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    target = args.out_dir / f'{args.date}-task-recovery-results.json'
    with target.open('x') as output:
        json.dump(report, output, ensure_ascii=False, indent=2)
    print(json.dumps(metrics, ensure_ascii=False))


if __name__ == '__main__':
    main()
