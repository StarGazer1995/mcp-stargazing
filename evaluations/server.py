"""Evaluation-only MCP adapter for the draft agent-native planning contract."""

from __future__ import annotations

import src.main  # noqa: F401  # Register the production 16-tool surface as realistic decoys.
from evaluations.planning_golden import SCENARIOS_BY_DATE, build_golden_service
from src.response import MCPError, format_response
from src.schemas import AgentPlanningRequest
from src.server_instance import mcp


@mcp.tool(
    name='plan_stargazing_session',
    description=(
        'Primary planning entry point for the frozen read-only agent evaluation dataset. '
        'Use it for an end-to-end location, night, observing-style, and equipment decision. '
        'The supported start dates are the dates stated in the evaluation questions.'
    ),
)
async def plan_stargazing_session(request: AgentPlanningRequest) -> dict:
    """Return one deterministic planning result without external network or write operations."""

    scenario = SCENARIOS_BY_DATE.get(request.start_date)
    if scenario is None:
        return MCPError(
            MCPError.CONFIGURATION_ERROR,
            'No frozen evaluation scenario exists for this start_date.',
            {'start_date': request.start_date},
        ).to_response()
    try:
        result = await build_golden_service(scenario).build_agent_plan(request)
    except MCPError as exc:
        return exc.to_response()
    return format_response(result.model_dump(mode='json'))


if __name__ == '__main__':
    mcp.run()
