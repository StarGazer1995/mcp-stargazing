"""Migration requests and frozen tool inventories must match the executable contract."""

import json
import re

from src.paths import PROJECT_ROOT
from src.schemas import AgentPlanningRequest


def test_migration_json_requests_are_valid_and_cover_each_location_mode():
    text = (PROJECT_ROOT / 'docs/v1-migration.md').read_text()
    requests = [
        AgentPlanningRequest.model_validate(json.loads(raw))
        for raw in re.findall(r'```json\n(.*?)\n```', text, flags=re.S)
    ]
    assert len(requests) == 3
    assert {bool(value.location.place_name) for value in requests} == {True, False}
    assert sum(value.location.bounds is not None for value in requests) == 1
    assert sum(value.location.center is not None for value in requests) == 1
    assert {value.equipment.preset.value for value in requests if value.equipment} == {
        'hope_d60_asi2600mc_air',
        'custom',
    }


def test_frozen_tools_are_present_in_public_readme_and_routing_audit():
    snapshot = json.loads((PROJECT_ROOT / 'tests/public_contract_v1.json').read_text())
    for filename in ('README.md', 'docs/tool-surface-audit.md'):
        text = (PROJECT_ROOT / filename).read_text()
        assert all(f'`{name}`' in text for name in snapshot['contract']['tool_schemas'])
