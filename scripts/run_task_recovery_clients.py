"""Run frozen recovery questions through installed clients; preserve auditable evidence."""

import argparse
import json
import os
import subprocess  # nosec B404 - fixed client executables, argv only, no shell
import tomllib
from pathlib import Path

from evaluations.task_recovery_golden import SCENARIOS_BY_KEY, task_id
from src.paths import PROJECT_ROOT


def score(scenario, answer, events):
    calls = [event for event in events if event['tool'] != 'get_tool_catalog']
    first = calls[0] if calls else {}
    response = first.get('response', {})
    first_is_result = first.get('tool') == 'get_area_analysis_result'
    contract_ok = (
        response.get('error', {}).get('code') == scenario.result_code
        if scenario.result_code and (first_is_result or scenario.key == 'runtime-changed')
        else response.get('_meta', {}).get('status') == 'success'
    )
    trace_ok = bool(calls) and all(
        event['tool'] in {'get_area_analysis_task', 'get_area_analysis_result'}
        and (event.get('arguments') or {}).get('task_id') == task_id(scenario.key)
        and not event.get('blocked')
        and not event.get('protocol_error')
        for event in calls
    )
    if scenario.first_tool == 'get_area_analysis_result':
        # Both direct retrieval and status -> retrieval are documented workflows.
        # A success status alone cannot prove the separate result cache expired.
        trace_ok = trace_ok and any(
            event['tool'] == 'get_area_analysis_result'
            and event.get('response', {}).get('error', {}).get('code') == scenario.result_code
            for event in calls
        )
    if scenario.key == 'paged-result':
        trace_ok = trace_ok and any(
            event['tool'] == 'get_area_analysis_result'
            and event['arguments'].get('page') == 2
            and event['arguments'].get('page_size') == 1
            and (event.get('response', {}).get('data', {}).get('items') or [{}])[0].get('name')
            == scenario.answer
            for event in calls
        )
    return {
        'first_tool': first.get('tool'),
        'tool_selection': first.get('tool') in scenario.allowed_first_tools,
        'first_call_contract': contract_ok,
        'trace_ok': trace_ok,
        'answer': answer,
        'expected_answer': scenario.answer,
        'exact_answer': answer == scenario.answer,
    }


def extract_answer(client, events):
    if client == 'codex':
        messages = [
            event['item'].get('text', '')
            for event in events
            if event.get('type') == 'item.completed'
            and event.get('item', {}).get('type') == 'agent_message'
        ]
    else:
        messages = [event.get('result', '') for event in events if event.get('type') == 'result']
    return messages[-1].strip() if messages else ''


def used_only_evaluation_tools(client, events):
    if client == 'codex':
        items = [event.get('item', {}) for event in events if event.get('type') == 'item.completed']
        return not any(
            item.get('type') in {'command_execution', 'file_change', 'web_search'}
            or (item.get('type') == 'mcp_tool_call' and item.get('server') != 'stargazing')
            for item in items
        )
    return all(
        block.get('name', '').startswith('mcp__stargazing__')
        for event in events
        for block in event.get('message', {}).get('content', [])
        if isinstance(block, dict) and block.get('type') == 'tool_use'
    )


def read_events(path):
    events = []
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                value = json.loads(line)
                if isinstance(value, dict):
                    events.append(value)
            except json.JSONDecodeError:
                continue  # Client diagnostics are retained verbatim in the raw log.
    return events


def codex_model_settings():
    """Reuse only model/provider selection, leaving plugins and other MCP servers isolated."""
    config_path = Path(os.getenv('CODEX_HOME', str(Path.home() / '.codex'))) / 'config.toml'
    if not config_path.is_file():
        return []
    config = tomllib.loads(config_path.read_text())
    settings = []
    for key in ('model', 'model_catalog_json'):
        if key in config:
            settings.extend(['-c', f'{key}={json.dumps(config[key])}'])
    provider_name = config.get('model_provider')
    provider = config.get('model_providers', {}).get(provider_name)
    if provider is not None:
        # Reuse the existing endpoint and authentication mode. Never copy secrets
        # or persist edits to user configuration. The alias avoids reserved IDs.
        selected = {
            key: provider[key]
            for key in (
                'name',
                'base_url',
                'wire_api',
                'requires_openai_auth',
                'env_key',
            )
            if key in provider
        }
        selected['supports_websockets'] = False
        inline = (
            '{' + ','.join(f'{key}={json.dumps(value)}' for key, value in selected.items()) + '}'
        )
        settings.extend(
            [
                '-c',
                'model_provider="task_eval_http"',
                '-c',
                f'model_providers.task_eval_http={inline}',
            ]
        )
    return settings


def command(client, directory, prompt, *, suite='recovery', case=None):
    python = str(PROJECT_ROOT / '.venv/bin/python')
    args = ['-m', 'evaluations.task_recovery_server', '--out-dir', str(directory)]
    if suite == 'actions':
        args = ['-m', 'evaluations.task_action_server', '--out-dir', str(directory), '--case', case]
    elif suite == 'planning':
        args = ['-m', 'evaluations.v1_planning_server', '--out-dir', str(directory)]
    if client == 'codex':
        return [
            'codex',
            'exec',
            '--ephemeral',
            '--ignore-user-config',
            '--approve-for-me',
            '--skip-git-repo-check',
            '-C',
            str(directory),
            '--json',
            *codex_model_settings(),
            '-c',
            f'mcp_servers.stargazing.command={json.dumps(python)}',
            '-c',
            f'mcp_servers.stargazing.args={json.dumps(args)}',
            '-c',
            f'mcp_servers.stargazing.cwd={json.dumps(str(PROJECT_ROOT))}',
            '-c',
            f'mcp_servers.stargazing.env={{PYTHONPATH={json.dumps(str(PROJECT_ROOT))}}}',
            prompt,
        ]
    config = {
        'mcpServers': {
            'stargazing': {
                'command': python,
                'args': args,
                'env': {'PYTHONPATH': str(PROJECT_ROOT)},
            }
        }
    }
    return [
        'claude',
        '-p',
        '--no-session-persistence',
        '--strict-mcp-config',
        '--mcp-config',
        json.dumps(config),
        '--tools',
        '',
        '--allowedTools',
        'mcp__stargazing__*',
        '--output-format',
        'stream-json',
        '--verbose',
        prompt,
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--client', choices=['codex', 'claude'], required=True)
    parser.add_argument('--suite', choices=['recovery', 'actions', 'planning'], default='recovery')
    parser.add_argument('--cases', nargs='+')
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--timeout-seconds', type=float, default=180)
    args = parser.parse_args()
    scenarios, scorer = SCENARIOS_BY_KEY, score
    if args.suite == 'actions':
        from evaluations.task_action_golden import SCENARIOS_BY_KEY as ACTION_SCENARIOS
        from evaluations.task_action_golden import score as action_score

        scenarios, scorer = ACTION_SCENARIOS, action_score
    elif args.suite == 'planning':
        from evaluations.v1_planning_golden import SCENARIOS_BY_KEY as PLANNING_SCENARIOS
        from evaluations.v1_planning_golden import score as planning_score

        scenarios, scorer = PLANNING_SCENARIOS, planning_score
    cases = list(scenarios) if args.cases is None else args.cases
    if not cases or len(set(cases)) != len(cases) or any(key not in scenarios for key in cases):
        parser.error('--cases must contain distinct cases from the selected suite')
    args.out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for key in cases:
        directory = args.out_dir.resolve() / key
        directory.mkdir()  # Refuse to mix retries with an existing case's evidence.
        scenario = scenarios[key]
        (directory / 'question.txt').write_text(scenario.prompt)
        invocation = command(args.client, directory, scenario.prompt, suite=args.suite, case=key)
        (directory / 'command.json').write_text(
            json.dumps(invocation, ensure_ascii=False, indent=2)
        )
        environment = dict(os.environ)
        for proxy_key in ('NO_PROXY', 'no_proxy'):
            environment[proxy_key] = ','.join(
                filter(
                    None,
                    [
                        environment.get(proxy_key),
                        '127.0.0.1',
                        'localhost',
                        '::1',
                    ],
                )
            )
        timed_out = False
        with (
            (directory / 'client.jsonl').open('w') as output,
            (directory / 'stderr.log').open('w') as errors,
        ):
            try:
                process = subprocess.run(  # nosec B603 - argv built from fixed commands and fixtures
                    invocation,
                    cwd=directory,
                    stdout=output,
                    stderr=errors,
                    stdin=subprocess.DEVNULL,
                    env=environment,
                    timeout=args.timeout_seconds,
                    check=False,
                )
                exit_code = process.returncode
            except subprocess.TimeoutExpired:
                timed_out, exit_code = True, None
        client_events = read_events(directory / 'client.jsonl')
        answer = extract_answer(args.client, client_events)
        result = scorer(scenario, answer, read_events(directory / 'calls.jsonl'))
        result.update(case=key, client=args.client, exit_code=exit_code, timed_out=timed_out)
        result['client_tools_ok'] = used_only_evaluation_tools(args.client, client_events)
        result['passed'] = (
            exit_code == 0
            and not timed_out
            and all(
                result[field]
                for field in (
                    'tool_selection',
                    'first_call_contract',
                    'trace_ok',
                    'exact_answer',
                    'client_tools_ok',
                )
            )
        )
        (directory / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
        results.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    with (args.out_dir / 'summary.json').open('x') as output:
        json.dump(results, output, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
