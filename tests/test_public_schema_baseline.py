"""Protect the pre-1.0 contract while allowing new, separately tested tools."""

import json
from pathlib import Path

import pytest

from scripts.capture_public_contract import capture_public_contract

BASELINE_PATH = Path(__file__).with_name('public_schema_baseline.json')


@pytest.mark.asyncio
async def test_pre1_public_schema_baseline():
    baseline = json.loads(BASELINE_PATH.read_text(encoding='utf-8'))['contract']
    current = await capture_public_contract()
    assert current['api_version'] == baseline['api_version']
    assert current['envelope_examples'] == baseline['envelope_examples']
    assert set(baseline['error_codes']) <= set(current['error_codes'])
    for section in ('tool_schemas', 'payload_schemas'):
        assert baseline[section].keys() <= current[section].keys(), (
            f'Existing {section} entries were removed or renamed'
        )
        for name, expected in baseline[section].items():
            assert current[section][name] == expected, (
                f'{section}/{name} changed from the pre-1.0 baseline. '
                'Review compatibility and document the migration before changing the baseline.'
            )
