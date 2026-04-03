"""Structured logging: structlog + JSON + redaction + request_id binding."""

from __future__ import annotations

import contextvars
import re
from typing import Any

import structlog

_request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("pnlclaw_request_id", default=None)

# Patterns that should be redacted in log output
_REDACT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(sk-[A-Za-z0-9]{3})[A-Za-z0-9]+"),  # OpenAI-style keys
    re.compile(r"(key-[A-Za-z0-9]{3})[A-Za-z0-9]+"),  # generic key-xxx
    re.compile(r"(secret[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9]{3})[A-Za-z0-9]+", re.IGNORECASE),
    re.compile(r"(token[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9]{3})[A-Za-z0-9]+", re.IGNORECASE),
    re.compile(r"(password[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9]{3})[A-Za-z0-9]+", re.IGNORECASE),
    re.compile(r"(Bearer\s+[A-Za-z0-9._\-]{5})[A-Za-z0-9._\-]+"),
    re.compile(r"(eyJ[A-Za-z0-9_\-]{5})[A-Za-z0-9._\-]+"),  # JWT-like
    re.compile(r"(api_key[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9]{3})[A-Za-z0-9]+", re.IGNORECASE),
    re.compile(r"(api_secret[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9]{3})[A-Za-z0-9]+", re.IGNORECASE),
    re.compile(r"(passphrase[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9]{3})[A-Za-z0-9]+", re.IGNORECASE),
    re.compile(r"(fernet:[A-Za-z0-9_/+]{5})[A-Za-z0-9_/+=]+"),  # Fernet tokens
    re.compile(r"(ghp_[A-Za-z0-9]{3})[A-Za-z0-9]+"),  # GitHub PAT
    re.compile(r"(gho_[A-Za-z0-9]{3})[A-Za-z0-9]+"),  # GitHub OAuth
    re.compile(r"(://[^:]+:)[^@]+(@)", re.IGNORECASE),  # URL credentials
]


def bind_request_id(request_id: str) -> None:
    """Bind a request ID to the current context for log correlation."""
    _request_id_var.set(request_id)


def get_request_id() -> str | None:
    """Return the current request ID, or None."""
    return _request_id_var.get()


def _redact_value(value: str) -> str:
    """Replace sensitive patterns in a string with masked versions."""
    result = value
    for pattern in _REDACT_PATTERNS:
        result = pattern.sub(r"\1***", result)
    return result


def _redact_processor(logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """structlog processor that redacts sensitive values."""
    for key, value in event_dict.items():
        if isinstance(value, str):
            event_dict[key] = _redact_value(value)
    return event_dict


def _request_id_processor(logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Inject the current request_id into every log entry."""
    rid = _request_id_var.get()
    if rid is not None:
        event_dict["request_id"] = rid
    return event_dict


def setup_logging(*, log_level: str = "INFO", json_format: bool = True) -> None:
    """Initialize structlog with JSON rendering, redaction, and request_id injection.

    Args:
        log_level: Minimum log level (e.g. "DEBUG", "INFO").
        json_format: If True, render logs as JSON. Otherwise use dev console format.
    """
    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        _request_id_processor,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        _redact_processor,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if json_format:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
