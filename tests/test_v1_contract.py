"""Gate the complete 1.0 surface independently of the historical 17-tool snapshot."""

import json
from pathlib import Path

import pytest
from conftest import _list_tool_entries

from scripts.capture_v1_contract import capture_v1_contract
from src.paths import PROJECT_ROOT

BASELINE_PATH = Path(__file__).with_name('public_contract_v1.json')


@pytest.mark.asyncio
async def test_v1_schema_models_annotations_and_envelopes_are_preserved():
    baseline = json.loads(BASELINE_PATH.read_text())['contract']
    current = await capture_v1_contract()
    assert baseline['api_version'] == current['api_version']
    assert baseline['envelope_examples'] == current['envelope_examples']
    assert set(baseline['error_codes']) <= set(current['error_codes'])
    for section in ('tool_schemas', 'payload_schemas', 'tool_annotations'):
        assert baseline[section].keys() <= current[section].keys()
        for name, expected in baseline[section].items():
            assert current[section][name] == expected, (
                f'Frozen 1.0 contract changed: {section}/{name}. '
                'Review compatibility and migration; do not refresh a snapshot to hide drift.'
            )


def test_real_http_tools_list_preserves_v1_schemas_and_annotations(running_mcp_server):
    baseline = json.loads(BASELINE_PATH.read_text())['contract']
    tools = {tool['name']: tool for tool in _list_tool_entries(*running_mcp_server)}
    for name, schemas in baseline['tool_schemas'].items():
        actual = tools[name]
        assert {key: actual.get(key) for key in schemas} == schemas
        assert actual.get('annotations') == baseline['tool_annotations'][name]


def test_freeze_includes_task_surface_and_finite_compatibility_policy():
    snapshot = json.loads(BASELINE_PATH.read_text())
    policy = json.loads((PROJECT_ROOT / 'docs/contract-policy.json').read_text())
    assert snapshot['target_release'] == policy['target_release'] == '1.0.0'
    assert len(snapshot['contract']['tool_schemas']) == 21
    assert {'AnalysisTask', 'AreaAnalysisRequest', 'AggregatedWeatherResponse'} <= set(
        snapshot['contract']['payload_schemas']
    )
    assert policy['minimum_notice_days'] == 90
    assert policy['minimum_subsequent_minor_releases'] == 2
    assert policy['removal_requires_next_major'] is True
    assert policy['deprecations'] == []  # Choosing a preferred tool does not start a notice period.
    assert set(policy['compatibility_tools']) == {
        'get_best_stargazing_plan',
        'get_multiday_stargazing_plan',
    }
    assert (PROJECT_ROOT / policy['schema_baseline']).resolve() == BASELINE_PATH.resolve()
