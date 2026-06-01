"""Structured logging configuration using structlog."""

from __future__ import annotations

import logging
import re
from typing import Any

import structlog

_SENSITIVE_PATTERN = re.compile(r"(password|token|secret|authorization|connection_string)", re.I)


def _redact_sensitive_fields(
    _logger: Any, _method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Replace values of keys matching sensitive patterns with '***'."""
    for key in list(event_dict.keys()):
        if _SENSITIVE_PATTERN.search(key):
            event_dict[key] = "***"
    return event_dict


def setup_logging(log_level: str = "INFO") -> None:
    """Configure structlog with JSON output and the standard processor chain."""

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            _redact_sensitive_fields,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Align stdlib logging level so third-party libraries respect the setting
    logging.basicConfig(format="%(message)s", level=getattr(logging, log_level.upper(), logging.INFO))


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger."""
    return structlog.get_logger(name)
