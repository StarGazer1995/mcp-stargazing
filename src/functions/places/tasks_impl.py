"""Public adapters for process-local background area-analysis tasks."""

import os
import threading
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from src.functions.places import impl as places
from src.logging_config import get_logger, set_request_id
from src.response import MCPError, format_error, format_response
from src.schemas.tasks import AnalysisTask, AreaAnalysisRequest
from src.server_instance import mcp
from src.services.area_tasks import AreaTaskService
from src.services.tasks import AnalysisTaskRegistry, TaskRegistryCode, TaskRegistryError

logger = get_logger(__name__)
_runtime: AreaTaskService | None = None
_runtime_lock = threading.Lock()
_REGISTRY_CODES = {
    TaskRegistryCode.INVALID_TASK_ID: MCPError.CONFIGURATION_ERROR,
    TaskRegistryCode.UNKNOWN_TASK: MCPError.TASK_NOT_FOUND,
    TaskRegistryCode.RUNTIME_CHANGED: MCPError.TASK_RUNTIME_CHANGED,
    TaskRegistryCode.CAPACITY_EXCEEDED: MCPError.TASK_CAPACITY_EXCEEDED,
    TaskRegistryCode.INVALID_TRANSITION: MCPError.TASK_UNAVAILABLE,
}


def get_area_task_service() -> AreaTaskService:
    global _runtime
    with _runtime_lock:
        if _runtime is None:
            try:
                registry = AnalysisTaskRegistry(
                    max_tasks=int(os.getenv('STARGAZING_TASK_MAX_RECORDS', '128')),
                    timeout_seconds=float(os.getenv('STARGAZING_TASK_TIMEOUT_SECONDS', '600')),
                    retention_seconds=float(os.getenv('STARGAZING_TASK_RETENTION_SECONDS', '3600')),
                )
                _runtime = AreaTaskService(
                    places.compute_area_locations,
                    places.ANALYSIS_CACHE,
                    registry,
                    max_workers=int(os.getenv('STARGAZING_TASK_WORKERS', '2')),
                    queue_capacity=int(os.getenv('STARGAZING_TASK_QUEUE_CAPACITY', '8')),
                )
            except (ValueError, OverflowError) as exc:
                raise MCPError(
                    MCPError.CONFIGURATION_ERROR,
                    'Invalid server background-task policy; check STARGAZING_TASK_* settings.',
                ) from exc
        return _runtime


def shutdown_area_tasks() -> None:
    with _runtime_lock:
        if _runtime is not None:
            _runtime.close()


def _respond(operation: Callable, task_id: str | None = None) -> dict[str, Any]:
    """Keep task-control errors distinct from a polled execution failure."""
    set_request_id()
    try:
        result = operation()
        if isinstance(result, AnalysisTask):
            return format_response(
                result.model_dump(mode='json'), task_id=result.task_id, progress=result.progress
            )
        meta = {'warnings': result.warnings} if result.warnings else None
        return format_response(
            result.result.model_dump(mode='json'), meta=meta, task_id=task_id, progress=1.0
        )
    except ValidationError as exc:
        errors = exc.errors(include_url=False, include_context=False, include_input=False)
        code = (
            MCPError.INVALID_COORDINATES
            if any(error['loc'] and error['loc'][0] == 'bounds' for error in errors)
            else MCPError.CONFIGURATION_ERROR
        )
        return format_error(
            code,
            'Invalid area-analysis request.',
            {'errors': errors},
            task_id=task_id,
        )
    except TaskRegistryError as exc:
        return format_error(
            _REGISTRY_CODES[exc.code],
            str(exc),
            {'reason': exc.code.value, 'next_action': 'resubmit_or_verify_task_id'},
            task_id=task_id,
        )
    except MCPError as exc:
        return format_error(exc.code, exc.message, exc.details, task_id=task_id)
    except Exception:
        logger.exception('Background area tool failed')
        return format_error(
            MCPError.EXTERNAL_API_ERROR,
            'Background area operation failed; inspect server logs.',
            task_id=task_id,
        )


@mcp.tool(
    annotations={
        'readOnlyHint': False,
        'destructiveHint': False,
        'idempotentHint': False,
        'openWorldHint': True,
    }
)
async def submit_area_analysis(request: AreaAnalysisRequest) -> dict[str, Any]:
    """Submit bounded background place analysis and return its task identifier.

    Use when a geographic area search may outlive one tool call. Poll with
    get_area_analysis_task, then page get_area_analysis_result after success.
    Do not use for a complete observing decision; use plan_stargazing_session.
    Active duplicate queries share a task. Completed retries may use cached data.
    """
    return _respond(
        lambda: get_area_task_service().submit(AreaAnalysisRequest.model_validate(request))
    )


@mcp.tool(
    annotations={
        'readOnlyHint': True,
        'destructiveHint': False,
        'idempotentHint': True,
        'openWorldHint': False,
    }
)
async def get_area_analysis_task(task_id: str) -> dict[str, Any]:
    """Poll an area task's state, deadline, failure, and normalized request.

    Use when you have a task_id from submit_area_analysis. Running progress is
    unknown; success does not guarantee the separate result cache still exists.
    Do not submit another job merely to poll; use get_area_analysis_result for data.
    """
    return _respond(lambda: get_area_task_service().status(task_id), task_id)


@mcp.tool(
    annotations={
        'readOnlyHint': False,
        'destructiveHint': False,
        'idempotentHint': True,
        'openWorldHint': False,
    }
)
async def cancel_area_analysis_task(task_id: str) -> dict[str, Any]:
    """Logically cancel queued/running area work and discard its late results.

    Use when a submitted task is no longer needed. Cancellation is idempotent;
    a running provider call keeps its execution slot until it actually finishes.
    Do not use to delete cached results or to interrupt another domain's tools.
    """
    return _respond(lambda: get_area_task_service().cancel(task_id), task_id)


@mcp.tool(
    annotations={
        'readOnlyHint': True,
        'destructiveHint': False,
        'idempotentHint': True,
        'openWorldHint': False,
    }
)
async def get_area_analysis_result(
    task_id: str,
    page: int = 1,
    page_size: int = 10,
) -> dict[str, Any]:
    """Page a successful area task's existing cached result without recomputing.

    Use after get_area_analysis_task reports succeeded. Pagination follows
    analysis_area and preserves resource_id. Missing or expired data requires
    resubmission of the normalized request, not silent recomputation.
    Do not use to poll queued/running tasks; use get_area_analysis_task instead.
    """

    def operation():
        task, cached = get_area_task_service().result(task_id)
        if task.request is None:
            raise MCPError(MCPError.CONFIGURATION_ERROR, 'Task request metadata is unavailable.')
        return places.build_analysis_page(
            cached, task.resource_id, task.request.road_radius_km, page, page_size
        )

    return _respond(operation, task_id)
