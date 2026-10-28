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
        'and supported preference fields have explicit defaults or are optional.\n'
        'A center/radius is a regional search, not a plan locked to the center point. '
        'The radius becomes an approximate search box, not a strict circular distance filter. '
        'Quietness/popularity adjustments require the corresponding preference flags.\n'
        'Pass request as a JSON object, not a JSON string; inspect resolved_location before '
        'describing a candidate as the exact user-specified site.\n'
        'Returns: normalized request, decision, alternatives, evidence, uncertainties, '
        'missing inputs, ranking-change conditions, and next actions in the standard envelope.\n'
        'Weather evidence uses dated night-hour forecasts; missing/partial coverage or no usable '
        'window makes the ranking provisional. Civil-dark windows are not astronomical darkness.\n'
        'Interpretation: recommendation_score is a relative ranking, not a probability or an '
        'absolute go/no-go threshold. _meta.status=success means execution succeeded; '
        'decision=null means no selected session. A null observation_window means no usable '
        'window was established, not an all-night opening. Inspect evidence, uncertainties, '
        'missing_inputs and next_actions even on success. nightly_weather_unavailable and '
        'no_usable_observation_window are high-uncertainty warnings; long_range_forecast '
        'requires a forecast recheck near departure. Never replace missing night hours with '
        'summary.current or summary.daily, or infer a provider from weather wording. '
        'Civil darkness means Sun below -6 degrees, not astronomical darkness at -18 degrees; '
        'its duration is not guaranteed exposure time. Popularity/quiet scores are heuristics, '
        'not measured noise or calibrated crowd probabilities.\n'
        'When equipment is supplied, decision.targets already contains equipment-matched targets; '
        "use that list to answer the selected session's target question without a second lookup.\n"
        'Keep the returned target order; do not compare scores across generic and equipment '
        'rankings. This is a synchronous call and can exceed a client default deadline; '
        'a timeout does not establish that a background planning task exists.\n'
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
