"""Verify frozen questions against actual MCP calls and the read-only audit guard."""

import json
import sys
from xml.etree import ElementTree

import pytest
from fastmcp import Client
from fastmcp.client.transports import StdioTransport

from evaluations.task_recovery_golden import SCENARIOS, build_frozen_service, task_id
from scripts.run_task_recovery_clients import score
from src.paths import PROJECT_ROOT


def test_fixture_states_have_distinct_recovery_meanings():
    service = build_frozen_service()
    try:
        for key, state in [
            ('queued', 'queued'),
            ('running', 'running'),
            ('failed', 'failed'),
            ('timed-out', 'timed_out'),
            ('cancelled-draining', 'cancelled'),
            ('expired-record', 'expired'),
        ]:
            assert service.status(task_id(key)).state == state
        assert service.status(task_id('running')).progress is None
        assert service.status(task_id('cancelled-draining')).execution_pending is True
    finally:
        service.close()


def test_xml_questions_match_executable_scenarios():
    root = ElementTree.parse(PROJECT_ROOT / 'evaluations/task_recovery_golden.xml').getroot()
    assert [(item.findtext('question'), item.findtext('answer')) for item in root] == [
        (scenario.prompt, scenario.answer) for scenario in SCENARIOS
    ]


def test_saved_client_report_matches_its_preserved_call_evidence():
    report = json.loads(
        (PROJECT_ROOT / 'evaluations/reports/2026-10-27-task-recovery-results.json').read_text()
    )
    scenarios = {scenario.key: scenario for scenario in SCENARIOS}
    assert set(report['results']) == {'codex', 'claude'}
    for client, rows in report['results'].items():
        assert {row['case'] for row in rows} == set(scenarios)
        for row in rows:
            recalculated = score(scenarios[row['case']], row['answer'], row['calls'])
            for key, value in recalculated.items():
                assert row[key] == value
            assert row['passed'] is True
            assert row['client_tools_ok'] is True
        for key in ('tool_selection', 'first_call_contract', 'trace_ok', 'exact_answer', 'passed'):
            assert report['metrics'][client][key] == sum(bool(row[key]) for row in rows)


@pytest.mark.asyncio
async def test_all_frozen_scenarios_through_real_stdio(tmp_path):
    transport = StdioTransport(
        sys.executable,
        ['-m', 'evaluations.task_recovery_server', '--out-dir', str(tmp_path)],
        cwd=str(PROJECT_ROOT),
        keep_alive=False,
    )
    async with Client(transport) as client:
        tools = await client.list_tools()
        assert len(tools) == 21
        for scenario in SCENARIOS:
            result = await client.call_tool(scenario.first_tool, {'task_id': task_id(scenario.key)})
            payload = result.structured_content
            if scenario.result_code:
                assert payload['error']['code'] == scenario.result_code
            else:
                assert payload['_meta']['status'] == 'success'
                if scenario.key == 'failed':
                    assert payload['data']['failure']['code'] == scenario.answer
                elif scenario.key == 'paged-result':
                    result = await client.call_tool(
                        'get_area_analysis_result',
                        {
                            'task_id': task_id(scenario.key),
                            'page': 2,
                            'page_size': 1,
                        },
                    )
                    assert result.structured_content['data']['items'][0]['name'] == scenario.answer
                elif scenario.key == 'cancelled-draining':
                    assert payload['data']['execution_pending'] is True
                elif scenario.key == 'expired-record':
                    assert payload['data']['state'] == 'expired'
        blocked = await client.call_tool(
            'cancel_area_analysis_task',
            {
                'task_id': task_id('running'),
            },
            raise_on_error=False,
        )
        assert blocked.is_error
        unchanged = await client.call_tool(
            'get_area_analysis_task', {'task_id': task_id('running')}
        )
        assert unchanged.structured_content['data']['state'] == 'running'
    events = [json.loads(line) for line in (tmp_path / 'calls.jsonl').read_text().splitlines()]
    assert len([event for event in events if event.get('blocked')]) == 1
    assert not any(event.get('protocol_error') for event in events)
