"""Project only the explicitly reviewed atmospheric additions onto the immutable v1 schema."""

import copy
import json

from src.paths import PROJECT_ROOT

ADDITIONS = {
    'CurrentWeather': ('atmosphere',),
    'HourlyForecastItem': ('atmosphere',),
    'NormalizedWeatherData': ('atmosphere_sources',),
    'WeatherSummary': ('atmosphere_sources',),
}
EXTENSION_PATH = PROJECT_ROOT / 'tests/weather_atmosphere_contract.json'


def extension_schema(current: dict, baseline: dict) -> dict:
    """Capture the added fields and definitions, never rewriting a historical baseline."""
    return {
        'properties': {
            name: {field: current['$defs'][name]['properties'][field] for field in fields}
            for name, fields in ADDITIONS.items()
        },
        'definitions': {
            name: schema
            for name, schema in current['$defs'].items()
            if name not in baseline['$defs']
        },
    }


def project_reviewed_weather_extension(current: dict, baseline: dict) -> dict:
    """Keep exact comparison for all old fields, plus exact validation of the new contract."""
    expected = json.loads(EXTENSION_PATH.read_text())
    assert extension_schema(current, baseline) == expected, 'Unreviewed atmospheric schema drift'
    projected = copy.deepcopy(current)
    for name, fields in ADDITIONS.items():
        definition = projected['$defs'][name]
        for field in fields:
            assert field not in definition.get('required', []), (
                'Atmospheric additions must be optional'
            )
            del definition['properties'][field]
    for name in expected['definitions']:
        del projected['$defs'][name]
    return projected
