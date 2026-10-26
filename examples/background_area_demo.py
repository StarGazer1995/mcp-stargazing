"""Submit, resume, cancel, and page background area analysis through MCP."""

import argparse
import asyncio
import json

from fastmcp import Client


async def run(args: argparse.Namespace) -> None:
    async with Client(args.url) as client:

        async def call(name: str, arguments: dict) -> dict:
            result = await client.call_tool(name, arguments)
            payload = result.structured_content
            if not isinstance(payload, dict):
                raise RuntimeError('Expected a structured JSON response.')
            if 'error' in payload:
                raise RuntimeError(json.dumps(payload, ensure_ascii=False))
            return payload['data']

        task_id = args.task_id
        if args.cancel:
            task = await call('cancel_area_analysis_task', {'task_id': task_id})
            print(json.dumps(task, ensure_ascii=False, indent=2))
            return
        if task_id is None:
            task = await call(
                'submit_area_analysis',
                {
                    'request': {
                        'bounds': {
                            'south': args.south,
                            'west': args.west,
                            'north': args.north,
                            'east': args.east,
                        },
                        'max_locations': args.max_locations,
                        'road_radius_km': 0,
                    }
                },
            )
            task_id = task['task_id']
        print(f'Task: {task_id}', flush=True)
        try:
            async with asyncio.timeout(args.wait_seconds):
                while True:
                    task = await call('get_area_analysis_task', {'task_id': task_id})
                    if task['state'] not in {'queued', 'running'}:
                        break
                    await asyncio.sleep(1)
        except TimeoutError:
            print(f'Polling stopped. Resume with --task-id {task_id}; task remains active.')
            return
        if task['state'] != 'succeeded':
            print(json.dumps(task, ensure_ascii=False, indent=2))
            return
        page = await call(
            'get_area_analysis_result',
            {'task_id': task_id, 'page': args.page, 'page_size': args.page_size},
        )
        print(json.dumps(page, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://localhost:3001/shttp')
    parser.add_argument('--task-id', help='Resume an existing task in the same server runtime.')
    parser.add_argument('--cancel', action='store_true', help='Explicitly cancel --task-id.')
    parser.add_argument('--south', type=float, default=39.5)
    parser.add_argument('--west', type=float, default=115.5)
    parser.add_argument('--north', type=float, default=40.5)
    parser.add_argument('--east', type=float, default=116.5)
    parser.add_argument('--max-locations', type=int, default=10)
    parser.add_argument('--page', type=int, default=1)
    parser.add_argument('--page-size', type=int, default=10)
    parser.add_argument('--wait-seconds', type=float, default=600)
    args = parser.parse_args()
    if args.cancel and not args.task_id:
        parser.error('--cancel requires --task-id')
    if args.wait_seconds <= 0:
        parser.error('--wait-seconds must be positive')
    asyncio.run(run(args))


if __name__ == '__main__':
    main()
