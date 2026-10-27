"""Isolated active-workflow server using production task adapters and actual workers."""

import argparse
import asyncio
import threading
from pathlib import Path

from fastmcp.exceptions import ToolError

from evaluations.area_task_server import controlled_compute
from evaluations.task_action_golden import SCENARIOS_BY_KEY, TASK_TOOLS, matches_request
from evaluations.task_recovery_server import RecoveryAudit
from src.analysis_cache import AnalysisCache
from src.functions.places import tasks_impl
from src.server_instance import mcp
from src.services.area_tasks import AreaTaskService
from src.services.tasks import AnalysisTaskRegistry


class ActionAudit(RecoveryAudit):
    def __init__(self, directory, started, provider_calls):
        super().__init__(directory / 'calls.jsonl')
        self.directory = directory
        self.started = started
        self.provider_calls = provider_calls

    async def on_call_tool(self, context, call_next):
        event = {'tool': context.message.name, 'arguments': context.message.arguments}
        allowed = event['tool'] in TASK_TOOLS | {'get_tool_catalog'}
        if event['tool'] == 'submit_area_analysis':
            allowed = allowed and matches_request((event['arguments'] or {}).get('request'))
        if not allowed:
            event['blocked'] = True
            self.write(event)
            raise ToolError('This isolated evaluation permits only the specified task workflow.')
        try:
            result = await call_next(context)
            if event['tool'] == 'submit_area_analysis':
                await asyncio.to_thread(self.started.wait, 2)
            event['response'] = result.structured_content
            event['provider_calls'] = len(self.provider_calls)
            self.write(event)
            return result
        except Exception:
            event['protocol_error'] = True
            self.write(event)
            raise
        finally:
            if event['tool'] == 'cancel_area_analysis_task':
                (self.directory / 'provider/release').touch()


def build_service(directory, key):
    started = threading.Event()
    calls = []

    def compute(query):
        calls.append(query)
        started.set()
        # Keep provider markers separate from the MCP call audit.
        return controlled_compute(directory / 'provider', query)

    provider = directory / 'provider'
    provider.mkdir()
    if key == 'submit-page':
        (provider / 'release').touch()

    service = AreaTaskService(compute, AnalysisCache(), AnalysisTaskRegistry(), max_workers=1)
    return service, ActionAudit(directory, started, calls)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--case', choices=list(SCENARIOS_BY_KEY), required=True)
    args = parser.parse_args()
    if not args.out_dir.is_dir():
        parser.error('--out-dir must exist')
    service, audit = build_service(args.out_dir, args.case)
    tasks_impl._runtime = service
    mcp.add_middleware(audit)
    try:
        mcp.run()
    finally:
        (args.out_dir / 'provider/release').touch()
        service.close()


if __name__ == '__main__':
    main()
