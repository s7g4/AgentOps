from __future__ import annotations

import contextvars
import logging
from collections.abc import MutableMapping
from typing import Any

import structlog

# Shared ContextVar so trace_id flows through async/sync call chains.
_trace_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
    "trace_id", default="-"
)


def bind_trace_id(trace_id: str) -> contextvars.Token[str]:
    """Set the active trace ID. Returns a token so callers can reset it."""
    return _trace_id_ctx.set(trace_id)


def reset_trace_id(token: contextvars.Token[str]) -> None:
    _trace_id_ctx.reset(token)


def _inject_trace_id(
    logger: Any,  # noqa: ANN401
    method_name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    event_dict["trace_id"] = _trace_id_ctx.get()
    return event_dict


def configure_structlog(log_level: str = "INFO") -> None:
    """Configure structlog with JSON output, ISO timestamps, and trace-id injection."""
    level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(
        format="%(message)s",
        level=level,
    )
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(level),
        processors=[
            structlog.contextvars.merge_contextvars,
            _inject_trace_id,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.CallsiteParameterAdder(
                [structlog.processors.CallsiteParameter.FILENAME]
            ),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger() -> Any:  # noqa: ANN401
    """Return a structlog bound logger. Typed as Any due to structlog's dynamic API."""
    return structlog.get_logger()
