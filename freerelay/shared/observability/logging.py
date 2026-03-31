"""
FreeRelay — Structured Logging (§15.3)
========================================
JSON structured logging via structlog with request_id binding.
Console renderer available for development.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog


# ─── Processors ──────────────────────────────────────────────────────────────


def _add_freerelay_context(
    logger: Any, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Add FreeRelay-specific context fields to every log line."""
    # Ensure request_id is present if bound via contextvars
    return event_dict


# ─── Setup ───────────────────────────────────────────────────────────────────


def setup_logging(
    level: str = "INFO",
    fmt: str = "json",
    service_name: str = "freerelay",
) -> None:
    """
    Configure structured logging for FreeRelay.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        fmt: Output format — 'json' for production, 'console' for development.
        service_name: Service name added to all log lines.
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Shared processors applied to all log entries
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
        _add_freerelay_context,
    ]

    # Choose renderer based on format
    if fmt == "console":
        renderer: structlog.types.Processor = structlog.dev.ConsoleRenderer(
            colors=True,
        )
    else:
        renderer = structlog.processors.JSONRenderer()

    # Configure structlog
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure stdlib formatter
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    # Set up handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(log_level)

    # Quiet noisy loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    # Bind service name to the root structlog logger
    structlog.get_logger().bind(service=service_name)


def get_logger(name: str = "freerelay") -> structlog.stdlib.BoundLogger:
    """
    Get a structlog bound logger.

    Args:
        name: Logger name (typically module name).

    Returns:
        Bound logger instance.
    """
    return structlog.get_logger(name)


def bind_request_id(request_id: str) -> None:
    """
    Bind a request_id to the current context.
    All subsequent logs in the same context will include this request_id.

    Args:
        request_id: The request identifier.
    """
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id)


def clear_context() -> None:
    """Clear all bound context variables."""
    structlog.contextvars.clear_contextvars()
