"""Expose production tools; dispatch the primary adapter to frozen planning dependencies."""

import argparse
from pathlib import Path

import src.main  # noqa: F401
from evaluations.planning_golden import SCENARIOS_BY_DATE, build_golden_service
from evaluations.task_recovery_server import RecoveryAudit
from src.functions.planning import agent_impl
from src.response import MCPError
from src.server_instance import mcp


class FrozenPlanner:
    async def build_agent_plan(self, request):
        scenario = SCENARIOS_BY_DATE.get(request.start_date)
        if scenario is None:
            raise MCPError(MCPError.CONFIGURATION_ERROR, 'No frozen case for this start_date.')
        return await build_golden_service(scenario).build_agent_plan(request)


class PlanningAudit(RecoveryAudit):
    allowed_tools = {'get_tool_catalog', 'plan_stargazing_session'}
    denied_message = 'This frozen evaluation permits primary planning and catalog reads only.'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', type=Path, required=True)
    args = parser.parse_args()
    if not args.out_dir.is_dir():
        parser.error('--out-dir must exist')
    agent_impl._build_planning_service = FrozenPlanner
    mcp.add_middleware(PlanningAudit(args.out_dir / 'calls.jsonl'))
    mcp.run()


if __name__ == '__main__':
    main()
