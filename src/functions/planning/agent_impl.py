"""Primary MCP adapter for agent-native stargazing planning."""

from typing import Any

from src.functions.planning.impl import _build_planning_service, _respond_with_mcp_error
from src.schemas import AgentPlanningRequest
from src.server_instance import mcp


@mcp.tool(
    name='plan_stargazing_session',
    description=(
        'Preferred end-to-end planning entry point for choosing when, where, and what to observe '
        'across one to seven nights.\n\n'
        'Use when: you need a complete observing decision or comparisons of places and nights.\n'
        'Do not use when: you only need raw weather, celestial facts, or task status.\n'
        'Requires: request.location (place name, center/radius, or exact bounds) and start_date; '
        'timezone, one-to-seven nights, observing goal, equipment preset/overrides, '
        'and constraints have explicit defaults or are optional.\n'
        'Returns: normalized request, decision, alternatives, evidence, uncertainties, '
        'missing inputs, ranking-change conditions, and next actions in the standard envelope.\n'
        'When equipment is supplied, decision.targets already contains equipment-matched targets; '
        "use that list to answer the selected session's target question without a second lookup.\n"
        'Follow-up: get_shooting_plan for an imaging schedule at the selected place/night; '
        'get_weather_by_position for updated weather facts. Inspect missing inputs and '
        'next actions before treating a degraded decision as final.'
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
