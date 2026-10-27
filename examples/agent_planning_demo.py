"""Call the primary planner with a user-intent JSON file and retain its full evidence."""

import argparse
import asyncio
import json
from pathlib import Path

from fastmcp import Client
from fastmcp.exceptions import ToolError


async def run(url, request: dict, *, timeout_seconds: float = 120) -> dict:
    async with Client(url, timeout=timeout_seconds) as client:
        result = await client.call_tool('plan_stargazing_session', {'request': request})
    payload = result.structured_content
    if not isinstance(payload, dict) or not {'data', 'error'} & payload.keys():
        raise ValueError('The server did not return the standard structured response.')
    return payload


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://localhost:3001/shttp')
    parser.add_argument(
        '--request', type=Path, required=True, help='User-intent request JSON file.'
    )
    parser.add_argument('--timeout-seconds', type=float, default=120)
    args = parser.parse_args(argv)
    if args.timeout_seconds <= 0:
        parser.error('--timeout-seconds must be positive')
    try:
        request = json.loads(args.request.read_text(encoding='utf-8'))
        if not isinstance(request, dict):
            raise ValueError('Request JSON must be an object.')
        payload = asyncio.run(run(args.url, request, timeout_seconds=args.timeout_seconds))
    except (OSError, ValueError, ToolError, TimeoutError) as exc:
        parser.exit(2, f'Planning request failed: {exc}\n')
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    # A success with decision=null is an actionable planning outcome, not a tool error.
    # Preserve uncertainties/missing_inputs/next_actions rather than indexing decision blindly.
    return 1 if 'error' in payload else 0


if __name__ == '__main__':
    raise SystemExit(main())
