"""The reviewed additive fields must not become a general exception to the frozen contract."""

import copy
import json

import pytest

from scripts.weather_contract_extension import ADDITIONS, project_reviewed_weather_extension
from src.paths import PROJECT_ROOT
from src.schemas.weather import AggregatedWeatherResponse


def schemas():
    baseline = json.loads((PROJECT_ROOT / 'tests/public_contract_v1.json').read_text())
    return (
        AggregatedWeatherResponse.model_json_schema(mode='serialization'),
        baseline['contract']['payload_schemas']['AggregatedWeatherResponse'],
    )


def test_reviewed_additions_preserve_every_existing_field():
    current, baseline = schemas()
    assert project_reviewed_weather_extension(current, baseline) == baseline
    policy = json.loads((PROJECT_ROOT / 'docs/contract-policy.json').read_text())
    extension = policy['compatible_extensions'][0]
    assert extension['added_optional_fields'] == {
        key: list(value) for key, value in ADDITIONS.items()
    }
    assert (PROJECT_ROOT / extension['schema_extension']).is_file()
    assert (PROJECT_ROOT / extension['review']).is_file()


@pytest.mark.parametrize('mutation', ['required', 'new-unit', 'old-field', 'extra-field'])
def test_unreviewed_drift_is_rejected(mutation):
    current, baseline = schemas()
    current = copy.deepcopy(current)
    if mutation == 'required':
        current['$defs']['CurrentWeather'].setdefault('required', []).append('atmosphere')
    elif mutation == 'new-unit':
        current['$defs']['AtmosphericState']['properties']['pm2_5_ug_m3']['description'] = 'μg/mL'
    elif mutation == 'old-field':
        current['$defs']['CurrentWeather']['properties']['humidity']['description'] = 'changed'
    else:
        current['$defs']['CurrentWeather']['properties']['unreviewed'] = {'type': 'number'}
    with pytest.raises(AssertionError):
        assert project_reviewed_weather_extension(current, baseline) == baseline
