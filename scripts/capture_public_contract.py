"""Capture the actual MCP schemas before adding another public tool.

Run as a module from the repository root. Existing snapshots are never replaced.
"""

import argparse
import asyncio
import json
from importlib.metadata import version
from pathlib import Path

import src.main  # noqa: F401 - register the production tool surface
from src.response import API_VERSION, format_error, format_response
from src.schemas import (
    AgentPlanningResult,
    AnalysisAreaResult,
    BestStargazingPlan,
    MultiNightStargazingPlan,
)
from src.schemas.error import ErrorCode
from src.server_instance import mcp

PAYLOAD_MODELS = (
    AgentPlanningResult,
    AnalysisAreaResult,
    BestStargazingPlan,
    MultiNightStargazingPlan,
)


async def capture_public_contract() -> dict:
    """Read SDK-generated schemas without executing any business tool."""
    tools = await mcp.get_tools()
    tool_schemas = {}
    for name, tool in sorted(tools.items()):
        wire = tool.to_mcp_tool()
        tool_schemas[name] = {
            'inputSchema': wire.inputSchema,
            'outputSchema': wire.outputSchema,
        }
    return {
        'api_version': API_VERSION,
        'tool_schemas': tool_schemas,
        'payload_schemas': {
            model.__name__: model.model_json_schema(mode='serialization')
            for model in PAYLOAD_MODELS
        },
        'error_codes': sorted(code.value for code in ErrorCode),
        'envelope_examples': {
            'success': format_response({}),
            'error': format_error(ErrorCode.CONFIGURATION_ERROR.value, 'Example failure'),
            'error_with_details': format_error(
                ErrorCode.CONFIGURATION_ERROR.value, 'Example failure', {'reason': 'example'}
            ),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--source-revision', required=True, help='Verified source commit SHA')
    args = parser.parse_args()
    snapshot = {
        'baseline': 'pre-1.0-public-contract',
        'source_revision': args.source_revision,
        'capture_versions': {
            package: version(package) for package in ('fastmcp', 'mcp', 'pydantic')
        },
        'contract': asyncio.run(capture_public_contract()),
    }
    destination = args.out_dir / 'public_schema_baseline.json'
    # Generation is explicit and exclusive: a baseline update must be a separate
    # reviewed change, never an accidental overwrite while running the tests.
    with destination.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + '\n')
    print(destination.resolve())


if __name__ == '__main__':
    main()
