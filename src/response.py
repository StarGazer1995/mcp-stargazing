from typing import Any

API_VERSION = '1.0.0'


def format_response(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Format a successful response with standard metadata.
    """
    response = {'data': data, '_meta': {'version': API_VERSION, 'status': 'success'}}
    if meta:
        response['_meta'].update(meta)
    return response


def format_error(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Format an error response with standard metadata.
    This is useful for returning "soft errors" that don't throw an exception,
    allowing the agent to handle the failure gracefully.
    """
    error_obj = {'code': code, 'message': message}
    if details:
        error_obj['details'] = details

    return {'error': error_obj, '_meta': {'version': API_VERSION, 'status': 'error'}}


class MCPError(Exception):
    """Base exception for application errors that should be reported to the agent."""

    # Standard error codes
    INVALID_COORDINATES = 'INVALID_COORDINATES'
    INVALID_TIMEZONE = 'INVALID_TIMEZONE'
    INVALID_TIME_FORMAT = 'INVALID_TIME_FORMAT'
    MISSING_API_KEY = 'MISSING_API_KEY'
    API_AUTH_FAILURE = 'API_AUTH_FAILURE'
    API_TIMEOUT = 'API_TIMEOUT'
    API_RATE_LIMIT = 'API_RATE_LIMIT'
    EXTERNAL_API_ERROR = 'EXTERNAL_API_ERROR'
    NETWORK_ERROR = 'NETWORK_ERROR'
    CONFIGURATION_ERROR = 'CONFIGURATION_ERROR'

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        self.code = code
        self.message = message
        self.details = details
        super().__init__(message)

    def to_response(self) -> dict[str, Any]:
        """Convert this error to a formatted response dict."""
        return format_error(self.code, self.message, self.details)
