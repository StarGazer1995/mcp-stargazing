from typing import Any, Dict, Optional
import os

API_VERSION = "1.0.0"

def format_response(data: Any, meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Format a successful response with standard metadata.
    """
    response = {
        "data": data,
        "_meta": {
            "version": API_VERSION,
            "status": "success"
        }
    }
    if meta:
        response["_meta"].update(meta)
    return response

def format_error(code: str, message: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Format an error response with standard metadata.
    This is useful for returning "soft errors" that don't throw an exception,
    allowing the agent to handle the failure gracefully.
    """
    error_obj = {
        "code": code,
        "message": message
    }
    if details:
        error_obj["details"] = details
        
    return {
        "error": error_obj,
        "_meta": {
            "version": API_VERSION,
            "status": "error"
        }
    }

class MCPError(Exception):
    """Base exception for application errors that should be reported to the agent."""
    def __init__(self, code: str, message: str, details: Optional[Dict[str, Any]] = None):
        self.code = code
        self.message = message
        self.details = details
        super().__init__(message)
