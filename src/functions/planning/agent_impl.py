"""Primary MCP adapter for agent-native stargazing planning."""

from typing import Any

from src.functions.planning.impl import _build_planning_service, _respond_with_mcp_error
from src.schemas import AgentPlanningRequest
from src.server_instance import mcp


@mcp.tool(
    name='plan_stargazing_session',
    description=(
        'Preferred end-to-end planning entry point for choosing when, where, and what to observe '
        'across one to seven nights. Use it with a place name, center/radius, or exact bounds and '
        'optional equipment; it returns a decision, alternatives, evidence, uncertainties, '
        'ranking-change conditions, and next actions. Do not use it for raw weather or celestial '
        'lookup requests.'
    ),
    annotations={
        'title': 'Plan Stargazing Session',
        'readOnlyHint': True,
        'destructiveHint': False,
        'idempotentHint': True,
        'openWorldHint': True,
    },
)
async def plan_stargazing_session(request: AgentPlanningRequest) -> dict[str, Any]:
    """Build one auditable, agent-native observing decision from user intent."""

    return await _respond_with_mcp_error(_build_planning_service().build_agent_plan(request))
