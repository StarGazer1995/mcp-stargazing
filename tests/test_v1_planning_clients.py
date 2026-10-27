"""Run the production primary adapter against every frozen scenario and reject guessed answers."""

import copy
import json
import sys

import pytest
from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from fastmcp.exceptions import ToolError

from evaluations.v1_planning_golden import SCENARIOS, score
from scripts.run_task_recovery_clients import read_events
from src.paths import PROJECT_ROOT


@pytest.mark.asyncio
async def test_production_adapter_schemas_and_all_planning_cases(tmp_path):
    transport = StdioTransport(
        command=sys.executable,
        args=['-m', 'evaluations.v1_planning_server', '--out-dir', str(tmp_path)],
        cwd=str(PROJECT_ROOT),
        env={'PYTHONPATH': str(PROJECT_ROOT)},
    )
    baseline = json.loads((PROJECT_ROOT / 'tests/public_contract_v1.json').read_text())['contract']
    async with Client(transport) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
        assert tools.keys() == baseline['tool_schemas'].keys()
        for name, expected in baseline['tool_schemas'].items():
            assert tools[name].inputSchema == expected['inputSchema']
            assert tools[name].outputSchema == expected['outputSchema']
        for scenario in SCENARIOS:
            result = await client.call_tool(
                'plan_stargazing_session',
                {'request': scenario.golden.request.model_dump(mode='json')},
            )
            assert result.structured_content['_meta']['status'] == 'success'
            event = read_events(tmp_path / 'calls.jsonl')[-1]
            graded = score(scenario, scenario.answer, [event])
            assert all(
                graded[field]
                for field in ('tool_selection', 'first_call_contract', 'trace_ok', 'exact_answer')
            ), scenario.key
            assert not score(scenario, scenario.answer, [])['trace_ok']
            wrong = copy.deepcopy(event)
            wrong['arguments']['request']['start_date'] = '2000-01-01'
            assert not score(scenario, scenario.answer, [wrong])['trace_ok']
            wrong = copy.deepcopy(event)
            wrong['response']['data'] = {}
            assert not score(scenario, scenario.answer, [wrong])['trace_ok']
            assert not score(scenario, scenario.answer, [event, event])['trace_ok']
        with pytest.raises(ToolError, match='primary planning'):
            await client.call_tool('get_local_datetime_info', {})
    assert read_events(tmp_path / 'calls.jsonl')[-1]['blocked'] is True


def test_preserved_client_evidence_keeps_full_runs_and_rechecks_distinct():
    report = json.loads(
        (PROJECT_ROOT / 'evaluations/reports/2026-10-27-v1-planning-results.json').read_text()
    )
    for client, rows in report['results'].items():
        assert {row['case'] for row in rows} == {scenario.key for scenario in SCENARIOS}
        scenarios = {scenario.key: scenario for scenario in SCENARIOS}
        assert report['metrics'][client]['passed'] == sum(row['passed'] for row in rows)
        for row in rows + report['startup_rechecks'][client]:
            grade = score(scenarios[row['case']], row['answer'], row['calls'])
            for field in ('tool_selection', 'first_call_contract', 'trace_ok', 'exact_answer'):
                assert grade[field] == row[field]
        failed = [row for row in rows if not row['passed']]
        assert [row['case'] for row in failed] == ['beginner-single-choice']
        assert not failed[0]['calls']
        assert report['startup_rechecks'][client][0]['passed'] is True
        assert report['coverage_after_rechecks'][client] == {
            'cases': 10,
            'covered_by_successful_trace': 10,
        }
