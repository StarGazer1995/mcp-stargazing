"""Qualify all frozen planning questions against the production tool description and adapter."""

import json
from dataclasses import dataclass

from evaluations.planning_golden import GOLDEN_SCENARIOS, GoldenScenario, extract_result_value
from src.schemas import AgentPlanningRequest, AgentPlanningResult


@dataclass(frozen=True)
class PlanningScenario:
    golden: GoldenScenario

    @property
    def key(self):
        return self.golden.scenario_id

    @property
    def answer(self):
        return self.golden.expected_answer

    @property
    def prompt(self):
        return (
            self.golden.question
            + '\nUser inputs: '
            + json.dumps(self.golden.request.model_dump(mode='json'), ensure_ascii=False)
            + '\nUse only the stargazing MCP tools to verify. Do not read files, execute commands, '
            'or use other servers. Return only the exact requested value without explanation.'
        )


SCENARIOS = tuple(PlanningScenario(scenario) for scenario in GOLDEN_SCENARIOS)
SCENARIOS_BY_KEY = {scenario.key: scenario for scenario in SCENARIOS}


def score(scenario, answer, events):
    calls = [event for event in events if event['tool'] != 'get_tool_catalog']
    first = calls[0] if calls else {}
    response = first.get('response') or {}
    request_ok = False
    try:
        request_ok = (
            AgentPlanningRequest.model_validate((first.get('arguments') or {}).get('request'))
            == scenario.golden.request
        )
    except (ValueError, TypeError):
        pass
    observed = None
    if response.get('_meta', {}).get('status') == 'success':
        try:
            observed = extract_result_value(
                AgentPlanningResult.model_validate(response['data']), scenario.golden.expected_path
            )
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            pass
    return {
        'first_tool': first.get('tool'),
        'tool_selection': first.get('tool') == 'plan_stargazing_session',
        'first_call_contract': response.get('_meta', {}).get('status') == 'success',
        'trace_ok': bool(
            len(calls) == 1
            and first.get('tool') == 'plan_stargazing_session'
            and not first.get('blocked')
            and not first.get('protocol_error')
            and request_ok
            and observed == scenario.answer
        ),
        'answer': answer,
        'expected_answer': scenario.answer,
        'exact_answer': answer == scenario.answer,
    }
