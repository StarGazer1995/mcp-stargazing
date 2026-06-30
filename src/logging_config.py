"""Structured logging with request-id propagation.

Configures structlog to produce timestamped, structured log entries.
A request_id is carried via contextvars so every log emitted during a
tool call automatically includes the request identity — no need to
thread a logger instance through the call stack.
"""

import sys
import uuid

import structlog


def get_request_id() -> str:
    """Return the current request-id, or empty string if none is set."""
    ctx = structlog.contextvars.get_contextvars()
    return ctx.get('request_id', '')


def set_request_id(request_id: str | None = None) -> str:
    """Bind a request-id for the current context.

    If *request_id* is omitted a short random id is generated.
    Returns the id that was bound.
    """
    if request_id is None:
        request_id = uuid.uuid4().hex[:12]
    structlog.contextvars.bind_contextvars(request_id=request_id)
    return request_id


def clear_request_id() -> None:
    """Remove all context variables bound for the current request."""
    structlog.contextvars.clear_contextvars()


def setup_logging(*, dev_mode: bool = False) -> None:
    """Configure structlog once at process startup."""
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt='iso'),
    ]

    if dev_mode or sys.stderr.isatty():
        renderer = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger for the given *name*."""
    return structlog.get_logger(name or __name__)
