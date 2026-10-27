"""Active AI workflows must be supported by a real task execution and exact trace."""

import asyncio
import copy
import json
import sys

import pytest
from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from fastmcp.exceptions import ToolError

from evaluations.task_action_golden import REQUEST, SCENARIOS, SCENARIOS_BY_KEY, score
from scripts.run_task_recovery_clients import read_events
from src.paths import PROJECT_ROOT


async def call(client, name, **arguments):
    result = (await client.call_tool(name, arguments)).structured_content
    assert result['_meta']['status'] == 'success', result
    return result['data']


@pytest.mark.asyncio
@pytest.mark.parametrize('scenario', SCENARIOS, ids=lambda value: value.key)
async def test_active_workflows_use_actual_worker_and_production_tools(tmp_path, scenario):
    transport = StdioTransport(
        command=sys.executable,
        args=[
            '-m',
            'evaluations.task_action_server',
            '--out-dir',
            str(tmp_path),
            '--case',
            scenario.key,
        ],
        cwd=str(PROJECT_ROOT),
        env={'PYTHONPATH': str(PROJECT_ROOT)},
    )
    async with Client(transport) as client:
        tools = await client.list_tools()
        assert len(tools) == 21
        task = await call(client, 'submit_area_analysis', request=REQUEST)
        task_id = task['task_id']
        if scenario.key == 'duplicate-cancel':
            duplicate = await call(client, 'submit_area_analysis', request=REQUEST)
            assert duplicate['task_id'] == task_id
        if scenario.key != 'submit-page':
            cancelled = await call(client, 'cancel_area_analysis_task', task_id=task_id)
            assert cancelled['state'] == 'cancelled'
            assert cancelled['execution_pending'] is True
        async with asyncio.timeout(10):
            while True:
                state = await call(client, 'get_area_analysis_task', task_id=task_id)
                if state['state'] in {'succeeded', 'cancelled'} and not state['execution_pending']:
                    break
                await asyncio.sleep(0.02)
        if scenario.key == 'submit-page':
            page = await call(
                client, 'get_area_analysis_result', task_id=task_id, page=2, page_size=1
            )
            assert page['items'][0]['name'] == scenario.answer
        else:
            assert state['result_revision'] is None  # No late publication after cancellation.
        events = read_events(tmp_path / 'calls.jsonl')
        result = score(scenario, scenario.answer, events)
        assert all(result[key] for key in ('tool_selection', 'first_call_contract', 'trace_ok'))
        assert len(read_events(tmp_path / 'provider/calls.jsonl')) == 1
        if scenario.key == 'duplicate-cancel':
            # Retain a real passing trace for mutation-based grader regression below.
            assert score(scenario, 'DIFFERENT', events)['exact_answer'] is False
            for mutation in (
                'wrong-id',
                'wrong-request',
                'wrong-resource',
                'missing-cancel',
                'missing-confirmation',
                'extra-worker',
                'blocked',
                'early-poll',
            ):
                changed = copy.deepcopy(events)
                if mutation == 'wrong-id':
                    changed[-1]['arguments']['task_id'] = 'fabricated'
                elif mutation == 'wrong-request':
                    changed[0]['arguments']['request']['max_locations'] = 3
                elif mutation == 'wrong-resource':
                    changed[1]['response']['data']['resource_id'] = 'another-query'
                elif mutation == 'missing-cancel':
                    changed = [e for e in changed if e['tool'] != 'cancel_area_analysis_task']
                elif mutation == 'missing-confirmation':
                    changed = [e for e in changed if e['tool'] != 'get_area_analysis_task']
                elif mutation == 'extra-worker':
                    changed[-1]['provider_calls'] = 2
                elif mutation == 'blocked':
                    changed[-1]['blocked'] = True
                else:
                    changed.insert(1, copy.deepcopy(changed[-1]))
                assert not score(scenario, scenario.answer, changed)['trace_ok'], mutation
        elif scenario.key == 'submit-page':
            for mutation in ('wrong-page', 'wrong-name', 'no-status', 'no-result'):
                changed = copy.deepcopy(events)
                if mutation == 'wrong-page':
                    changed[-1]['arguments']['page'] = 1
                elif mutation == 'wrong-name':
                    changed[-1]['response']['data']['items'][0]['name'] = 'Guessed Valley'
                elif mutation == 'no-status':
                    changed = [e for e in changed if e['tool'] != 'get_area_analysis_task']
                else:
                    changed.pop()
                assert not score(scenario, scenario.answer, changed)['trace_ok'], mutation


def test_answer_without_execution_evidence_cannot_pass():
    scenario = SCENARIOS_BY_KEY['cancel-running']
    result = score(scenario, scenario.answer, [])
    assert result['exact_answer'] is True
    assert not result['trace_ok']
    assert not result['first_call_contract']


@pytest.mark.asyncio
async def test_active_fixture_blocks_other_tools_and_unrelated_queries(tmp_path):
    transport = StdioTransport(
        command=sys.executable,
        args=[
            '-m',
            'evaluations.task_action_server',
            '--out-dir',
            str(tmp_path),
            '--case',
            'submit-page',
        ],
        cwd=str(PROJECT_ROOT),
        env={'PYTHONPATH': str(PROJECT_ROOT)},
    )
    async with Client(transport) as client:
        for name, args in (
            ('get_local_datetime', {}),
            ('submit_area_analysis', {'request': {**REQUEST, 'max_locations': 3}}),
        ):
            with pytest.raises(ToolError, match='isolated evaluation'):
                await client.call_tool(name, args)
    assert all(row['blocked'] for row in read_events(tmp_path / 'calls.jsonl'))
    assert not (tmp_path / 'provider/calls.jsonl').exists()


def test_preserved_two_client_evidence_regrades_without_answer_only_shortcuts():
    report = json.loads(
        (PROJECT_ROOT / 'evaluations/reports/2026-10-27-task-actions-results.json').read_text()
    )
    assert set(report['results']) == {'codex', 'claude'}
    for client, rows in report['results'].items():
        assert {row['case'] for row in rows} == set(SCENARIOS_BY_KEY)
        for row in rows:
            result = score(SCENARIOS_BY_KEY[row['case']], row['answer'], row['calls'])
            for field in ('tool_selection', 'first_call_contract', 'trace_ok', 'exact_answer'):
                assert result[field] is True
                assert result[field] == row[field]
            assert row['client_tools_ok'] is True
            assert row['passed'] is True
        assert report['metrics'][client]['passed'] == len(rows)
