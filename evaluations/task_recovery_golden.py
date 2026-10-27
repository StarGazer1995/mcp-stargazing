"""Frozen, read-only task-recovery questions backed by production task adapters."""

from concurrent.futures import Future
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import NAMESPACE_URL, uuid5

from src.analysis_cache import AnalysisCache, generate_cache_key
from src.response import MCPError
from src.schemas import AreaAnalysisRequest, StargazingLocation, TaskFailure
from src.services.area_tasks import AreaTaskService
from src.services.tasks import AnalysisTaskRegistry

RUNTIME_ID = uuid5(NAMESPACE_URL, 'stargazing/task-eval/runtime').hex
NOW = datetime(2026, 10, 27, 12, tzinfo=UTC)


def task_id(key: str) -> str:
    runtime = '0' * 32 if key == 'runtime-changed' else RUNTIME_ID
    return f'{runtime}:{uuid5(NAMESPACE_URL, "stargazing/task-eval/" + key).hex}'


@dataclass(frozen=True)
class RecoveryScenario:
    key: str
    question: str
    answer: str
    first_tool: str = 'get_area_analysis_task'
    result_code: str | None = None

    @property
    def allowed_first_tools(self) -> set[str]:
        if self.first_tool == 'get_area_analysis_result':
            return {'get_area_analysis_task', 'get_area_analysis_result'}
        return {self.first_tool}

    @property
    def prompt(self) -> str:
        return (
            f'{self.question}\n任务编号：{task_id(self.key)}\n'
            '只使用观星 MCP 查询工具核实，不提交、不取消、不重算，不读取本地文件。'
            '只输出要求的单个答案，不加解释。'
        )


SCENARIOS = (
    RecoveryScenario(
        'queued',
        '我保存了一个区域分析任务。只查一次，现在应继续等还是重交？仅回复 WAIT 或 RESUBMIT。',
        'WAIT',
    ),
    RecoveryScenario(
        'running',
        '区域分析还没给地点。只查一次，现在应继续等还是重交？仅回复 WAIT 或 RESUBMIT。',
        'WAIT',
    ),
    RecoveryScenario(
        'failed',
        '请核实任务为什么没有地点结果。状态查询成功不等于分析成功；仅返回分析失败的 error code。',
        'NETWORK_ERROR',
    ),
    RecoveryScenario(
        'timed-out',
        '我不确定是仍在分析还是已超时。请查询并只返回任务 state 的原始字符串。',
        'timed_out',
    ),
    RecoveryScenario(
        'cancelled-draining',
        '任务已经取消，我想知道后台执行占用是否释放。仅回复 WAIT_FOR_EXECUTION 或 READY_TO_RETRY。',
        'WAIT_FOR_EXECUTION',
    ),
    RecoveryScenario(
        'paged-result',
        '请先确认任务成功，再读取每页 1 个地点的第 2 页。只返回该页地点名称。',
        'Recovery Valley',
    ),
    RecoveryScenario(
        'missing-cache',
        '这个任务之前已成功。请直接尝试读取结果，核实缓存是否还在。'
        '若结果失效仅回复 RESUBMIT；若可读仅回复 READABLE。',
        'RESUBMIT',
        'get_area_analysis_result',
        MCPError.TASK_RESULT_EXPIRED,
    ),
    RecoveryScenario(
        'replaced-cache',
        '请直接读取这个已成功任务的原结果，不能用同查询的新版本冒充。'
        '若原结果已失效仅回复 RESUBMIT；若可读仅回复 READABLE。',
        'RESUBMIT',
        'get_area_analysis_result',
        MCPError.TASK_RESULT_EXPIRED,
    ),
    RecoveryScenario(
        'runtime-changed',
        '我重连后保留了旧任务编号。请核实编号能否继续查询。'
        '应重交原请求回复 RESUBMIT；仍可等待回复 WAIT。',
        'RESUBMIT',
        result_code=MCPError.TASK_RUNTIME_CHANGED,
    ),
    RecoveryScenario(
        'expired-record',
        '我很久没看这个任务了。请核实元数据状态，只返回任务 state 的原始字符串。',
        'expired',
    ),
)
SCENARIOS_BY_KEY = {scenario.key: scenario for scenario in SCENARIOS}


def build_frozen_service() -> AreaTaskService:
    """Seed deterministic metadata/cache; no real provider work is scheduled."""
    clock = [NOW]
    with patch(
        'src.services.tasks.uuid4',
        return_value=uuid5(NAMESPACE_URL, 'stargazing/task-eval/runtime'),
    ):
        registry = AnalysisTaskRegistry(now=lambda: clock[0])
    cache = AnalysisCache()

    def forbidden_compute(_query):
        raise AssertionError('Frozen recovery evaluation must not compute places.')

    service = AreaTaskService(forbidden_compute, cache, registry)
    for index, scenario in enumerate(SCENARIOS):
        if scenario.key == 'runtime-changed':
            continue
        clock[0] = NOW - timedelta(hours=2) if scenario.key == 'expired-record' else NOW
        if scenario.key == 'timed-out':
            clock[0] -= timedelta(seconds=601)
        request = AreaAnalysisRequest(
            bounds={'south': 30 + index / 10, 'west': 119, 'north': 32, 'east': 120},
            road_radius_km=0,
        )
        resource_id = generate_cache_key(**request.search_parameters())
        with patch(
            'src.services.tasks.uuid4',
            return_value=uuid5(NAMESPACE_URL, 'stargazing/task-eval/' + scenario.key),
        ):
            task = registry.submit(resource_id, request)
        if scenario.key != 'queued':
            registry.start(task.task_id)
        if scenario.key == 'failed':
            registry.fail(task.task_id, TaskFailure(code=MCPError.NETWORK_ERROR, message='Offline'))
        elif scenario.key == 'cancelled-draining':
            registry.cancel(task.task_id)
        elif scenario.key in {'paged-result', 'missing-cache', 'replaced-cache', 'expired-record'}:
            locations = [
                StargazingLocation(name='Recovery Ridge', lat=30.1, lon=119.1),
                StargazingLocation(name='Recovery Valley', lat=30.2, lon=119.2),
            ]
            registry.succeed(task.task_id, publish=lambda: cache.set(resource_id, locations))
            if scenario.key == 'missing-cache':
                cache._cache.pop(resource_id)
            elif scenario.key == 'replaced-cache':
                cache.set(resource_id, [])
        if scenario.key in {'queued', 'running', 'timed-out', 'cancelled-draining'}:
            # Frozen physical-occupancy metadata, not a scheduled worker. Actual
            # execution/draining behavior is covered by P5.2/P5.3 integration tests.
            future = Future()
            if scenario.key != 'queued':
                future.set_running_or_notify_cancel()
            service._jobs[task.task_id] = future
        clock[0] = NOW
        registry.get(task.task_id)  # Materialize timeout/retention at the frozen query time.
    return service
