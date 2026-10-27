"""Active task workflows: real execution, returned identities, and strict trace grading."""

import json
from dataclasses import dataclass

from src.schemas import AreaAnalysisRequest

REQUEST = {
    'bounds': {'south': 30, 'west': 119, 'north': 31, 'east': 120},
    'road_radius_km': 0,
    'max_locations': 2,
}
TASK_TOOLS = {
    'submit_area_analysis',
    'get_area_analysis_task',
    'get_area_analysis_result',
    'cancel_area_analysis_task',
}


@dataclass(frozen=True)
class ActionScenario:
    key: str
    question: str
    answer: str

    @property
    def prompt(self):
        return (
            self.question
            + '\n区域分析请求：'
            + json.dumps(REQUEST, ensure_ascii=False)
            + '\n只使用观星 MCP 工具，不读取本地文件、不执行命令。'
            '这是隔离验收服务，允许按要求提交和取消；不请求完整观测规划。'
            '任务编号必须使用实际返回值。只输出要求的单个答案。'
        )


SCENARIOS = (
    ActionScenario(
        'submit-page',
        '请新建这个区域的后台地点分析，查询状态直到成功，然后读取每页 1 条的第 2 页。'
        '只返回该页地点名称。',
        'Recovery Valley',
    ),
    ActionScenario(
        'cancel-running',
        '请提交这个区域的后台地点分析，然后取消刚返回的任务，查询确认取消状态。'
        '不要取结果或重交。仅返回最后查询的 state。',
        'cancelled',
    ),
    ActionScenario(
        'duplicate-cancel',
        '请连续提交两次完全相同的区域分析请求，核对活动任务是否复用同一个编号，'
        '然后取消该任务并查询确认。不要取结果或再次重交。'
        '编号相同且确认取消只回复 REUSED_AND_CANCELLED，否则回复 DIFFERENT。',
        'REUSED_AND_CANCELLED',
    ),
)
SCENARIOS_BY_KEY = {scenario.key: scenario for scenario in SCENARIOS}


def matches_request(value):
    try:
        return AreaAnalysisRequest.model_validate(value) == AreaAnalysisRequest.model_validate(
            REQUEST
        )
    except (ValueError, TypeError):
        return False


def score(scenario, answer, events):
    calls = [event for event in events if event['tool'] != 'get_tool_catalog']
    first = calls[0] if calls else {}
    first_data = first.get('response', {}).get('data', {})
    identity = first_data.get('task_id')
    resource = first_data.get('resource_id')
    trace_ok = bool(identity and resource) and matches_request(first_data.get('request'))
    submits, cancellations, statuses, pages = [], [], [], []
    succeeded = cancelled = False
    for event in calls:
        tool = event['tool']
        args = event.get('arguments') or {}
        response = event.get('response') or {}
        data = response.get('data') or {}
        trace_ok = bool(
            trace_ok
            and tool in TASK_TOOLS
            and not event.get('blocked')
            and not event.get('protocol_error')
            and response.get('_meta', {}).get('status') == 'success'
            and event.get('provider_calls') == 1
        )
        if tool == 'submit_area_analysis':
            submits.append(event)
            trace_ok = trace_ok and matches_request(args.get('request'))
            trace_ok = trace_ok and data.get('task_id') == identity
            trace_ok = trace_ok and data.get('resource_id') == resource
            trace_ok = trace_ok and not cancellations and not statuses and not pages
        else:
            trace_ok = trace_ok and args.get('task_id') == identity and bool(submits)
            if tool == 'get_area_analysis_task':
                statuses.append(event)
                trace_ok = trace_ok and data.get('task_id') == identity
                trace_ok = trace_ok and data.get('resource_id') == resource
                succeeded = succeeded or data.get('state') == 'succeeded'
                cancelled = cancelled or (bool(cancellations) and data.get('state') == 'cancelled')
            elif tool == 'cancel_area_analysis_task':
                cancellations.append(event)
                trace_ok = trace_ok and data.get('state') == 'cancelled'
                trace_ok = trace_ok and data.get('task_id') == identity
                trace_ok = trace_ok and data.get('resource_id') == resource
            elif tool == 'get_area_analysis_result':
                pages.append(event)
                trace_ok = bool(
                    trace_ok
                    and succeeded
                    and args.get('page') == 2
                    and args.get('page_size') == 1
                    and data.get('resource_id') == resource
                    and [item.get('name') for item in data.get('items', [])] == [scenario.answer]
                )
    if scenario.key == 'submit-page':
        trace_ok = trace_ok and len(submits) == 1 and bool(pages) and not cancellations
    else:
        expected_submits = 2 if scenario.key == 'duplicate-cancel' else 1
        trace_ok = bool(
            trace_ok
            and len(submits) == expected_submits
            and cancellations
            and cancelled
            and not pages
        )
    return {
        'first_tool': first.get('tool'),
        'tool_selection': first.get('tool') == 'submit_area_analysis',
        'first_call_contract': first.get('response', {}).get('_meta', {}).get('status')
        == 'success',
        'trace_ok': bool(trace_ok),
        'answer': answer,
        'expected_answer': scenario.answer,
        'exact_answer': answer == scenario.answer,
    }
