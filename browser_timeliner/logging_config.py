"""Centralized logging utilities for Browser Timeliner.

This module provides structured logging suitable for enterprise deployments.
It supports correlation identifiers, JSON or console-friendly formatting, and
configuration via environment variables or explicit arguments.
"""

from __future__ import annotations

import json
import logging
import logging.config
import os
import sys
import uuid
from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

_LOG_LEVEL_ENV_VAR = "BROWSER_TIMELINER_LOG_LEVEL"
_LOG_FORMAT_ENV_VAR = "BROWSER_TIMELINER_LOG_FORMAT"
_DEFAULT_LEVEL = "INFO"
_DEFAULT_FORMAT = "console"

_correlation_id: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)


@dataclass(slots=True)
class LogConfig:
    """Configuration parameters for Browser Timeliner logging."""

    level: str = _DEFAULT_LEVEL
    log_format: str = _DEFAULT_FORMAT
    stream: Any = sys.stderr


class CorrelationIdFilter(logging.Filter):
    """Inject correlation ID into log records."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401 - required signature
        record.correlation_id = get_correlation_id() or "-"
        return True


class JsonFormatter(logging.Formatter):
    """Render log records as structured JSON."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401 - override
        timestamp = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()
        payload: Dict[str, Any] = {
            "timestamp": timestamp,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": getattr(record, "correlation_id", "-"),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        for key, value in record.__dict__.items():
            if key.startswith("_"):
                continue
            if key in payload:
                continue
            if key in {
                "args",
                "created",
                "exc_text",
                "filename",
                "funcName",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "msg",
                "name",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "stack_info",
                "thread",
                "threadName",
                "message",
            }:
                continue
            payload[key] = value
        return json.dumps(payload, ensure_ascii=False)


def _resolve_level(level: Optional[str]) -> str:
    if level is None:
        level = os.getenv(_LOG_LEVEL_ENV_VAR, _DEFAULT_LEVEL)
    level = str(level).upper()
    if level not in logging._nameToLevel:  # type: ignore[attr-defined]
        return _DEFAULT_LEVEL
    return level


def _resolve_format(fmt: Optional[str]) -> str:
    if fmt is None:
        fmt = os.getenv(_LOG_FORMAT_ENV_VAR, _DEFAULT_FORMAT)
    fmt = str(fmt).lower()
    if fmt not in {"json", "console"}:
        return _DEFAULT_FORMAT
    return fmt


def configure_logging(*, level: Optional[str] = None, log_format: Optional[str] = None, stream: Any = None) -> None:
    """Configure application-wide logging.

    Parameters can be supplied directly or via environment variables.
    Supported formats: ``json`` (default) and ``console``.
    """

    resolved_level = _resolve_level(level)
    resolved_format = _resolve_format(log_format)
    target_stream = stream or sys.stderr

    formatters: Dict[str, Dict[str, Any]] = {
        "json": {
            "()": JsonFormatter,
        },
        "console": {
            "format": "%(asctime)s | %(levelname)s | %(name)s | %(correlation_id)s | %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    }

    handlers: Dict[str, Dict[str, Any]] = {
        "default": {
            "class": "logging.StreamHandler",
            "stream": target_stream,
            "level": resolved_level,
            "filters": ["correlation"],
            "formatter": resolved_format,
        }
    }

    logging_config: Dict[str, Any] = {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "correlation": {
                "()": CorrelationIdFilter,
            }
        },
        "formatters": formatters,
        "handlers": handlers,
        "root": {
            "level": resolved_level,
            "handlers": ["default"],
        },
    }

    logging.config.dictConfig(logging_config)


def set_correlation_id(value: Optional[str]) -> None:
    """Set the correlation identifier for the current context."""

    _correlation_id.set(value)


def generate_correlation_id() -> str:
    """Generate a new correlation identifier."""

    return str(uuid.uuid4())


def get_correlation_id() -> Optional[str]:
    """Return the active correlation identifier if present."""

    return _correlation_id.get()


def clear_correlation_id() -> None:
    """Clear the correlation identifier for the current context."""

    set_correlation_id(None)


class LogContext:
    """Context manager for temporarily setting a correlation ID."""

    def __init__(self, correlation_id: Optional[str] = None):
        self._previous_token: Optional[Token] = None
        self._correlation_id = correlation_id or generate_correlation_id()

    def __enter__(self) -> str:
        self._previous_token = _correlation_id.set(self._correlation_id)
        return self._correlation_id

    def __exit__(self, exc_type, exc, exc_tb) -> None:  # noqa: D401 - context manager signature
        if self._previous_token is not None:
            _correlation_id.reset(self._previous_token)
        else:
            clear_correlation_id()


def get_logger(name: str) -> logging.Logger:
    """Return a ``logging.Logger`` instance."""

    return logging.getLogger(name)
