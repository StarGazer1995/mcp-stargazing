"""The migration example calls the production primary adapter without dropping degradation."""

import json

import pytest

from evaluations.planning_golden import GOLDEN_SCENARIOS, build_golden_service
from examples import agent_planning_demo
from src.functions.planning import agent_impl
from src.server_instance import mcp


@pytest.mark.asyncio
@pytest.mark.parametrize('scenario_id', ['hope-d60-equipment-target', 'empty-candidates-action'])
async def test_example_keeps_full_primary_response(scenario_id, monkeypatch):
    # Select by stable scenario intent rather than depending on array ordering.
    scenario = next(item for item in GOLDEN_SCENARIOS if item.scenario_id == scenario_id)
    monkeypatch.setattr(
        agent_impl, '_build_planning_service', lambda: build_golden_service(scenario)
    )
    payload = await agent_planning_demo.run(mcp._mcp, scenario.request.model_dump(mode='json'))
    assert payload['_meta']['status'] == 'success'
    assert {
        'decision',
        'alternatives',
        'evidence',
        'uncertainties',
        'missing_inputs',
        'would_change_if',
        'next_actions',
    } <= payload['data'].keys()
    if scenario_id == 'empty-candidates-action':
        assert payload['data']['decision'] is None
        assert payload['data']['next_actions'][0]['action'] == 'expand_search_area'
    else:
        assert payload['data']['decision']['targets'][0]['name'] == 'M31'


def test_example_preserves_structured_errors_and_exit_status(tmp_path, monkeypatch, capsys):
    request = tmp_path / 'request.json'
    request.write_text('{}')

    async def failed(*_args, **_kwargs):
        return {'error': {'code': 'INVALID_TIMEZONE'}, '_meta': {'status': 'error'}}

    monkeypatch.setattr(agent_planning_demo, 'run', failed)
    assert agent_planning_demo.main(['--request', str(request)]) == 1
    assert json.loads(capsys.readouterr().out)['error']['code'] == 'INVALID_TIMEZONE'
