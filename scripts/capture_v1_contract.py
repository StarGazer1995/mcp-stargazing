"""Capture the reviewed 1.0 surface without replacing the historical pre-1.0 baseline."""

import argparse
import asyncio
import json
from importlib.metadata import version
from pathlib import Path

from scripts.capture_public_contract import capture_public_contract
from src.response import format_error, format_response
from src.schemas import (
    AggregatedWeatherResponse,
    AnalysisTask,
    AreaAnalysisRequest,
    CelestialPosition,
    ConstellationInfo,
    LightPollutionGrid,
    MoonInfo,
    NightlyForecast,
    RiseSet,
    VisiblePlanet,
)
from src.server_instance import mcp

ADDITIONAL_PAYLOAD_MODELS = (
    AnalysisTask,
    AreaAnalysisRequest,
    CelestialPosition,
    ConstellationInfo,
    LightPollutionGrid,
    MoonInfo,
    NightlyForecast,
    RiseSet,
    VisiblePlanet,
    AggregatedWeatherResponse,
)


async def capture_v1_contract() -> dict:
    contract = await capture_public_contract()
    contract['payload_schemas'].update(
        {
            model.__name__: model.model_json_schema(mode='serialization')
            for model in ADDITIONAL_PAYLOAD_MODELS
        }
    )
    tools = await mcp.get_tools()
    contract['tool_annotations'] = {
        name: wire.annotations.model_dump(mode='json', exclude_none=True)
        if wire.annotations is not None
        else None
        for name, tool in sorted(tools.items())
        for wire in [tool.to_mcp_tool()]
    }
    contract['envelope_examples'].update(
        {
            'task_success': format_response({}, task_id='opaque-task', progress=0.0),
            'task_error': format_error(
                'TASK_NOT_READY', 'Example pending task', task_id='opaque-task'
            ),
        }
    )
    return contract


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--source-revision', required=True)
    args = parser.parse_args()
    snapshot = {
        'baseline': '1.0-public-contract',
        'target_release': '1.0.0',
        'source_revision': args.source_revision,
        'capture_versions': {
            package: version(package) for package in ('fastmcp', 'mcp', 'pydantic')
        },
        'contract': asyncio.run(capture_v1_contract()),
    }
    destination = args.out_dir / 'public_contract_v1.json'
    with destination.open('x', encoding='utf-8') as output:
        output.write(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + '\n')
    print(destination.resolve())


if __name__ == '__main__':
    main()
