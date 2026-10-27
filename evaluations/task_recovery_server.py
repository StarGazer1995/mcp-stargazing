"""Read-only stdio evaluation surface with frozen task states and call auditing."""

import argparse
import json
from pathlib import Path

from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware

import src.main  # noqa: F401
from evaluations.task_recovery_golden import build_frozen_service
from src.functions.places import tasks_impl
from src.server_instance import mcp

ALLOWED_TOOLS = {'get_tool_catalog', 'get_area_analysis_task', 'get_area_analysis_result'}


class RecoveryAudit(Middleware):
    """Keep all production tools discoverable but prevent any non-query execution."""

    allowed_tools = ALLOWED_TOOLS
    denied_message = 'This frozen evaluation permits task/status reads only.'

    def __init__(self, path: Path):
        self.path = path

    async def on_call_tool(self, context, call_next):
        event = {'tool': context.message.name, 'arguments': context.message.arguments}
        if event['tool'] not in self.allowed_tools:
            event['blocked'] = True
            self.write(event)
            raise ToolError(self.denied_message)
        try:
            result = await call_next(context)
        except Exception:
            event['protocol_error'] = True
            self.write(event)
            raise
        event['response'] = result.structured_content
        self.write(event)
        return result

    def write(self, event):
        with self.path.open('a', encoding='utf-8') as output:
            output.write(json.dumps(event, ensure_ascii=False) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', type=Path, required=True)
    args = parser.parse_args()
    if not args.out_dir.is_dir():
        parser.error('--out-dir must exist')
    tasks_impl._runtime = build_frozen_service()
    mcp.add_middleware(RecoveryAudit(args.out_dir / 'calls.jsonl'))
    mcp.run()


if __name__ == '__main__':
    main()
