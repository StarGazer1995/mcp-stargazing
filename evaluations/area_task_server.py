"""Isolated task-recovery harness: real MCP runtime, controlled place provider.

This entry point is only for acceptance tests. It writes gate/call markers under
the explicit control directory and exposes the production tools without adding
test-only control tools. It never contacts the real geographic providers.
"""

import argparse
import json
import threading
import time
from pathlib import Path

import src.main  # noqa: F401
from src.functions.places import impl as places
from src.schemas import StargazingLocation
from src.server_instance import mcp


def controlled_compute(control_dir: Path, query: dict) -> list[StargazingLocation]:
    with (control_dir / 'calls.jsonl').open('a', encoding='utf-8') as output:
        output.write(json.dumps(query) + '\n')
    (control_dir / 'started').touch()
    deadline = time.monotonic() + 30
    waiter = threading.Event()
    while not (control_dir / 'release').exists():
        if time.monotonic() >= deadline:
            raise TimeoutError('Acceptance harness gate was not released.')
        waiter.wait(0.02)
    return [
        StargazingLocation(name='Recovery Ridge', lat=30.1, lon=119.1, score=80),
        StargazingLocation(name='Recovery Valley', lat=30.2, lon=119.2, score=75),
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--control-dir', type=Path, required=True)
    parser.add_argument('--port', type=int, required=True)
    args = parser.parse_args()
    if not args.control_dir.is_dir():
        parser.error('--control-dir must be an existing test workspace')
    places.compute_area_locations = lambda query: controlled_compute(args.control_dir, query)
    mcp.run(
        transport='streamable-http',
        host='127.0.0.1',
        port=args.port,
        path='/shttp',
        log_level='warning',
    )


if __name__ == '__main__':
    main()
