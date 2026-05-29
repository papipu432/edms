"""Structured logging configuration using structlog."""

import contextvars
import logging
import re
import sys

import structlog

from app.core.config import settings

request_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)

# Pattern for sensitive keys (case-insensitive)
_SENSITIVE_PATTERN = re.compile(
    r"(password|token|secret|key|authorization|cookie)", re.IGNORECASE
)


def _filter_sensitive_data(
    logger: logging.Logger, method_name: str, event_dict: dict
) -> dict:
    """Replace values for sensitive keys with '***'."""
    for key in list(event_dict.keys()):
        if _SENSITIVE_PATTERN.search(key):
            event_dict[key] = "***"
    return event_dict


def _add_request_id(
    logger: logging.Logger, method_name: str, event_dict: dict
) -> dict:
    """Inject request_id from context variable into log entries."""
    request_id = request_id_ctx.get()
    if request_id is not None:
        event_dict["request_id"] = request_id
    return event_dict


def setup_logging() -> None:
    """Configure structlog for the application.

    Uses JSON output when LOG_FORMAT=json (production) and colored console
    output when LOG_FORMAT=text (development).
    """
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        _add_request_id,
        _filter_sensitive_data,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.LOG_FORMAT == "json":
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)
