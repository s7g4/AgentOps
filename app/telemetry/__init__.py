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

5. **No-op when disabled**.
   All functions check ``settings.otel_enabled`` and return a no-op tracer
   when OTel is off, so call sites never need conditional logic.

Usage
─────
Set environment variables before startup:

    OTEL_ENABLED=true
    OTEL_ENDPOINT=http://otel-collector:4317   # or Jaeger OTLP endpoint
    OTEL_SERVICE_NAME=agentops

Then instrument spans in the runtime::

    from app.telemetry.otel import get_tracer

    with get_tracer().start_as_current_span("classify") as span:
        result = await classifier.classify(message)
        span.set_attribute("intent", result.intent)
        span.set_attribute("confidence", result.confidence)
"""

from __future__ import annotations

import logging

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger(__name__)

_tracer: trace.Tracer | None = None
_provider: TracerProvider | None = None


def configure_otel(
    service_name: str,
    endpoint: str,
) -> None:
    """Initialise the global TracerProvider and wire up the OTLP exporter.

    Call once at application startup (inside the FastAPI lifespan handler).
    Safe to call multiple times — subsequent calls are no-ops.
    """
    global _tracer, _provider  # noqa: PLW0603

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

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": "2.0.0",
            "deployment.environment": "production",
        }
    )

    exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
    processor = BatchSpanProcessor(exporter)

    provider = TracerProvider(resource=resource)
    provider.add_span_processor(processor)

    # Register as the global provider so opentelemetry.trace.get_tracer() works.
    trace.set_tracer_provider(provider)

    _provider = provider
    _tracer = provider.get_tracer("agentops.runtime")

    logger.info("OpenTelemetry configured (endpoint=%s, service=%s)", endpoint, service_name)


def get_tracer() -> trace.Tracer:
    """Return the active tracer.

    Returns the configured OTel tracer when OTEL_ENABLED=true, or a no-op
    tracer from the default provider otherwise.  Call sites need no conditional
    checks — ``start_as_current_span`` on a no-op tracer is a zero-cost context
    manager.
    """
    if _tracer is not None:
        return _tracer
    # Return a no-op tracer — spans created from it are discarded.
    return trace.get_tracer("agentops.noop")


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
