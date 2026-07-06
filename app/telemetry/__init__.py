"""OpenTelemetry instrumentation for AgentOps.

Design decisions
────────────────
1. **Opt-in via OTEL_ENABLED**.
   OTel adds ~5ms startup overhead and requires a running collector.
   Disabled by default so local dev and tests are unaffected.

2. **OTLP gRPC exporter**.
   Works with any OpenTelemetry-compatible backend: Jaeger, Tempo, Datadog,
   Honeycomb, etc. via a collector sidecar or direct ingest.

3. **FastAPI auto-instrumentation**.
   ``FastAPIInstrumentor`` creates a root span per HTTP request automatically,
   capturing method, route, and status code as attributes.

4. **Manual spans for each agent stage**.
   Use ``get_tracer().start_as_current_span(name)`` inside the runtime to
   produce child spans for classify → plan → tool_exec → verify → respond.
   This gives per-stage latency breakdowns in the trace waterfall.

5. **No-op when disabled or not installed**.
   All functions check ``settings.otel_enabled`` and return a no-op tracer
   when OTel is off or the SDK is not installed, so call sites never need
   conditional logic.

Usage
─────
Set environment variables before startup:

    OTEL_ENABLED=true
    OTEL_ENDPOINT=http://otel-collector:4317   # or Jaeger OTLP endpoint
    OTEL_SERVICE_NAME=agentops

Then instrument spans in the runtime::

    from app.telemetry import get_tracer

    with get_tracer().start_as_current_span("classify") as span:
        result = await classifier.classify(message)
        span.set_attribute("intent", result.intent)
        span.set_attribute("confidence", result.confidence)
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any

from app import __version__

logger = logging.getLogger(__name__)

# ── Lazy OTel imports ─────────────────────────────────────────────────────────
# The opentelemetry SDK is in the optional [otel] extras group and may not be
# installed (e.g. CI, local dev).  We guard all SDK imports behind try/except
# and provide a lightweight no-op tracer shim so the rest of the codebase can
# call get_tracer() unconditionally.

try:
    from opentelemetry import trace as _otel_trace
    from opentelemetry.sdk.resources import Resource as _Resource
    from opentelemetry.sdk.trace import TracerProvider as _TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor as _BatchSpanProcessor

    _HAS_OTEL = True
except ImportError:
    _HAS_OTEL = False

_tracer: Any = None
_provider: Any = None


# ── No-op shim ────────────────────────────────────────────────────────────────
# When OTel is not installed, get_tracer() returns this shim.  It implements
# start_as_current_span() as a zero-cost context manager so all call sites
# (``with get_tracer().start_as_current_span("name"):``) work without error.


class _NoopSpan:
    """Minimal span-like object that does nothing."""

    def set_attribute(self, key: str, value: object) -> None:  # noqa: ARG002
        pass

    def set_status(self, *args: object, **kwargs: object) -> None:
        pass

    def record_exception(self, exc: BaseException) -> None:  # noqa: ARG002
        pass


class _NoopTracer:
    """Minimal tracer that returns no-op spans."""

    @contextmanager  # type: ignore[arg-type]
    def start_as_current_span(self, name: str, **kwargs: object) -> Any:  # noqa: ARG002
        yield _NoopSpan()


_NOOP_TRACER = _NoopTracer()


def configure_otel(
    service_name: str,
    endpoint: str,
) -> None:
    """Initialise the global TracerProvider and wire up the OTLP exporter.

    Call once at application startup (inside the FastAPI lifespan handler).
    Safe to call multiple times — subsequent calls are no-ops.
    """
    global _tracer, _provider  # noqa: PLW0603

    if not _HAS_OTEL:
        logger.warning(
            "opentelemetry SDK is not installed. "
            "Install it with: pip install 'agentops[otel]'"
        )
        return

    if _provider is not None:
        return  # already initialised

    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (  # noqa: PLC0415
            OTLPSpanExporter,
        )
    except ImportError:
        logger.warning(
            "opentelemetry-exporter-otlp-proto-grpc is not installed. "
            "Install it with: pip install 'agentops[otel]'"
        )
        return

    resource = _Resource.create(
        {
            "service.name": service_name,
            "service.version": __version__,
            "deployment.environment": "production",
        }
    )

    exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
    processor = _BatchSpanProcessor(exporter)

    provider = _TracerProvider(resource=resource)
    provider.add_span_processor(processor)

    # Register as the global provider so opentelemetry.trace.get_tracer() works.
    _otel_trace.set_tracer_provider(provider)

    _provider = provider
    _tracer = provider.get_tracer("agentops.runtime")

    logger.info("OpenTelemetry configured (endpoint=%s, service=%s)", endpoint, service_name)


def get_tracer() -> Any:
    """Return the active tracer.

    Returns the configured OTel tracer when OTEL_ENABLED=true and the SDK
    is installed, or a no-op tracer otherwise.  Call sites need no conditional
    checks — ``start_as_current_span`` on the no-op tracer is a zero-cost
    context manager.
    """
    if _tracer is not None:
        return _tracer
    if _HAS_OTEL:
        return _otel_trace.get_tracer("agentops.noop")
    return _NOOP_TRACER


def instrument_fastapi(app: object) -> None:
    """Auto-instrument a FastAPI app to emit HTTP spans.

    Creates a root span for every HTTP request with attributes:
    ``http.method``, ``http.route``, ``http.status_code``.

    Must be called after ``configure_otel`` for spans to be exported.
    """
    if _provider is None:
        return  # OTel not configured — skip instrumentation

    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor  # noqa: PLC0415

        FastAPIInstrumentor.instrument_app(app)  # type: ignore[arg-type]
        logger.info("FastAPI auto-instrumentation enabled")
    except ImportError:
        logger.warning(
            "opentelemetry-instrumentation-fastapi is not installed. "
            "Install it with: pip install 'agentops[otel]'"
        )


def shutdown_otel() -> None:
    """Flush pending spans and shut down the exporter.

    Call during application shutdown (lifespan cleanup) to ensure all
    in-flight spans are exported before the process exits.
    """
    global _provider, _tracer  # noqa: PLW0603
    if _provider is not None:
        _provider.shutdown()
        _provider = None
        _tracer = None
