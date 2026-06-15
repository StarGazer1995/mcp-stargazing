"""Standard error codes for the MCP Stargazing server.

Maps to the existing MCPError codes in src/response.py.
"""

from enum import StrEnum


class ErrorCode(StrEnum):
    """Standardized error codes for structured error responses."""

    INVALID_COORDINATES = "INVALID_COORDINATES"
    INVALID_TIMEZONE = "INVALID_TIMEZONE"
    INVALID_TIME_FORMAT = "INVALID_TIME_FORMAT"
    MISSING_API_KEY = "MISSING_API_KEY"
    API_AUTH_FAILURE = "API_AUTH_FAILURE"
    API_TIMEOUT = "API_TIMEOUT"
    API_RATE_LIMIT = "API_RATE_LIMIT"
    EXTERNAL_API_ERROR = "EXTERNAL_API_ERROR"
    NETWORK_ERROR = "NETWORK_ERROR"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
