from typing import Any

from src.schemas.error import ErrorCode

API_VERSION = '1.0.0'


def format_response(
    data: Any,
    meta: dict[str, Any] | None = None,
    progress: float | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    """
    Format a successful response with standard metadata.

    Reserved fields for future long-task / streaming support:
        progress: 0.0–1.0 progress indicator (present only when set).
        task_id:  opaque identifier used to resume or poll a long-running task.
    """
    response = {'data': data, '_meta': {'version': API_VERSION, 'status': 'success'}}
    if progress is not None:
        response['_meta']['progress'] = progress
    if task_id is not None:
        response['_meta']['task_id'] = task_id
    if meta:
        response['_meta'].update(meta)
    return response


def format_error(
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    """
    Format an error response with standard metadata.
    This is useful for returning "soft errors" that don't throw an exception,
    allowing the agent to handle the failure gracefully.

    Reserved fields for future long-task / streaming support:
        task_id: opaque identifier used to correlate errors with a long-running task.
    """
    error_obj = {'code': code, 'message': message}
    if details:
        error_obj['details'] = details

    meta = {'version': API_VERSION, 'status': 'error'}
    if task_id is not None:
        meta['task_id'] = task_id

    return {'error': error_obj, '_meta': meta}


class MCPError(Exception):
    """Base exception for application errors that should be reported to the agent.

    Error codes are backed by the :class:`ErrorCode` StrEnum (see
    ``src/schemas/error.py``).  Class-level constants are provided for
    backward compatibility and resolve to the same string values.
    """

    # Standard error codes — backed by ErrorCode StrEnum for type safety
    INVALID_COORDINATES = ErrorCode.INVALID_COORDINATES.value
    INVALID_TIMEZONE = ErrorCode.INVALID_TIMEZONE.value
    INVALID_TIME_FORMAT = ErrorCode.INVALID_TIME_FORMAT.value
    MISSING_API_KEY = ErrorCode.MISSING_API_KEY.value
    API_AUTH_FAILURE = ErrorCode.API_AUTH_FAILURE.value
    API_TIMEOUT = ErrorCode.API_TIMEOUT.value
    API_RATE_LIMIT = ErrorCode.API_RATE_LIMIT.value
    EXTERNAL_API_ERROR = ErrorCode.EXTERNAL_API_ERROR.value
    NETWORK_ERROR = ErrorCode.NETWORK_ERROR.value
    CONFIGURATION_ERROR = ErrorCode.CONFIGURATION_ERROR.value

    def __init__(
        self,
        code: str | ErrorCode,
        message: str,
        details: dict[str, Any] | None = None,
    ):
        self.code = code if isinstance(code, str) else code.value
        self.message = message
        self.details = details
        super().__init__(message)

    def to_response(self) -> dict[str, Any]:
        """Convert this error to a formatted response dict."""
        return format_error(self.code, self.message, self.details)
