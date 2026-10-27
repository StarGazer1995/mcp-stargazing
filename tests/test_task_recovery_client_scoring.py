"""Client acceptance must be supported by real, correct tool traces."""

import json
import sys
from types import SimpleNamespace

import pytest

from evaluations.task_recovery_golden import SCENARIOS_BY_KEY, task_id
from scripts import run_task_recovery_clients as runner
from scripts.run_task_recovery_clients import extract_answer, score, used_only_evaluation_tools


def event(key, tool='get_area_analysis_task', response=None, **extra):
    return {
        'tool': tool,
        'arguments': {'task_id': task_id(key)},
        'response': response or {'_meta': {'status': 'success'}},
        **extra,
    }


def test_correct_answer_without_mcp_evidence_is_not_accepted():
    result = score(SCENARIOS_BY_KEY['running'], 'WAIT', [])
    assert result['exact_answer'] is True
    assert result['trace_ok'] is False
    assert result['tool_selection'] is False
    assert result['first_call_contract'] is False


@pytest.mark.parametrize('change', ['wrong-task', 'blocked', 'protocol-error', 'wrong-tool'])
def test_correct_answer_cannot_hide_wrong_or_denied_calls(change):
    call = event('running')
    if change == 'wrong-task':
        call['arguments']['task_id'] = task_id('queued')
    elif change == 'blocked':
        call['blocked'] = True
    elif change == 'protocol-error':
        call['protocol_error'] = True
    else:
        call['tool'] = 'submit_area_analysis'
    assert score(SCENARIOS_BY_KEY['running'], 'WAIT', [call])['trace_ok'] is False


def test_expected_business_error_is_a_successful_contract_observation():
    scenario = SCENARIOS_BY_KEY['missing-cache']
    call = event(
        'missing-cache',
        'get_area_analysis_result',
        {'error': {'code': 'TASK_RESULT_EXPIRED'}, '_meta': {'status': 'error'}},
    )
    result = score(scenario, 'RESUBMIT', [call])
    assert result['first_call_contract'] is True
    assert result['trace_ok'] is True
    call['response']['error']['code'] = 'CONFIGURATION_ERROR'
    assert score(scenario, 'RESUBMIT', [call])['first_call_contract'] is False


def test_cache_recovery_accepts_status_then_retrieval_but_rejects_guessing():
    scenario = SCENARIOS_BY_KEY['missing-cache']
    status = event('missing-cache')
    status_only = score(scenario, 'RESUBMIT', [status])
    assert status_only['tool_selection'] is True
    assert status_only['first_call_contract'] is True
    assert status_only['trace_ok'] is False
    result = event(
        'missing-cache', 'get_area_analysis_result', {'error': {'code': 'TASK_RESULT_EXPIRED'}}
    )
    assert score(scenario, 'RESUBMIT', [status, result])['trace_ok'] is True
    result['response']['error']['code'] = 'TASK_NOT_READY'
    assert score(scenario, 'RESUBMIT', [status, result])['trace_ok'] is False


def test_pagination_requires_the_requested_page_and_a_nonempty_actual_result():
    scenario = SCENARIOS_BY_KEY['paged-result']
    first = event('paged-result')
    second = event('paged-result', 'get_area_analysis_result', {'data': {'items': []}})
    second['arguments'].update(page=2, page_size=1)
    assert not score(scenario, scenario.answer, [first, second])['trace_ok']
    second['response']['data']['items'] = [{'name': scenario.answer}]
    assert score(scenario, scenario.answer, [first, second])['trace_ok']
    second['arguments']['page'] = 1
    assert not score(scenario, scenario.answer, [first, second])['trace_ok']


def test_builtin_execution_is_not_a_valid_shortcut_for_client_acceptance():
    assert not used_only_evaluation_tools(
        'codex',
        [
            {
                'type': 'item.completed',
                'item': {'type': 'command_execution'},
            }
        ],
    )
    assert not used_only_evaluation_tools(
        'claude',
        [
            {
                'message': {'content': [{'type': 'tool_use', 'name': 'Bash'}]},
            }
        ],
    )
    assert used_only_evaluation_tools(
        'claude',
        [
            {
                'message': {
                    'content': [
                        {'type': 'tool_use', 'name': 'mcp__stargazing__get_area_analysis_task'}
                    ]
                },
            }
        ],
    )
    assert (
        extract_answer(
            'codex',
            [
                {
                    'type': 'item.completed',
                    'item': {
                        'type': 'agent_message',
                        'text': ' WAIT\n',
                    },
                }
            ],
        )
        == 'WAIT'
    )
    assert extract_answer('claude', [{'type': 'result', 'result': 'WAIT'}]) == 'WAIT'


def test_runner_keeps_case_identity_when_setting_local_proxy_bypass(tmp_path, monkeypatch):
    output_dir = tmp_path / 'output'

    def fake_run(_command, **kwargs):
        assert kwargs['stdin'] == runner.subprocess.DEVNULL
        assert '127.0.0.1' in kwargs['env']['NO_PROXY']
        kwargs['stdout'].write(json.dumps({'type': 'result', 'result': 'WAIT'}) + '\n')
        (kwargs['cwd'] / 'calls.jsonl').write_text(json.dumps(event('running')) + '\n')
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(runner.subprocess, 'run', fake_run)
    monkeypatch.setattr(
        sys,
        'argv',
        [
            'runner',
            '--client',
            'claude',
            '--cases',
            'running',
            '--out-dir',
            str(output_dir),
        ],
    )
    runner.main()
    result = json.loads((output_dir / 'running/result.json').read_text())
    assert result['case'] == 'running'
    assert result['passed'] is True


def test_model_selection_reuses_endpoint_without_copying_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv('CODEX_HOME', str(tmp_path))
    (tmp_path / 'config.toml').write_text("""
model = "configured-model"
model_provider = "existing"
[model_providers.existing]
name = "Existing provider"
base_url = "http://127.0.0.1:8787/backend-api/codex"
wire_api = "responses"
requires_openai_auth = true
api_key = "test-secret-must-not-be-copied"
""")
    settings = ' '.join(runner.codex_model_settings())
    assert 'configured-model' in settings
    assert 'http://127.0.0.1:8787/backend-api/codex' in settings
    assert 'supports_websockets=false' in settings
    assert 'test-secret-must-not-be-copied' not in settings
