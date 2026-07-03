from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.config.settings import load_settings
from app.logging.structured_logger import configure_structlog
from app.middleware.auth import APIKeyMiddleware
from app.middleware.rate_limit import RateLimitConfig, RateLimitMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan handler.

    Runs startup logic before the first request and cleanup after the last.
    Using lifespan (over @app.on_event) is the modern FastAPI pattern as of
    0.93+ — on_event is deprecated.
    """
    settings = load_settings()
    configure_structlog(log_level=settings.log_level)

    # ── OpenTelemetry (opt-in) ────────────────────────────────────────────────
    if settings.otel_enabled:
        from app.telemetry import configure_otel, instrument_fastapi  # noqa: PLC0415

        configure_otel(
            service_name=settings.otel_service_name,
            endpoint=settings.otel_endpoint,
        )
        instrument_fastapi(app)

    # Eagerly instantiate singletons to catch mis-configuration at startup,
    # not on the first request under production load.
    from app.api.deps import get_runtime, get_tool_registry, get_trace_store  # noqa: PLC0415

    app.state.runtime = get_runtime()
    app.state.tool_registry = get_tool_registry()
    app.state.trace_store = get_trace_store()

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    store = getattr(app.state, "trace_store", None)
    if store is not None and hasattr(store, "close"):
        await store.close()

    if settings.otel_enabled:
        from app.telemetry import shutdown_otel  # noqa: PLC0415

        shutdown_otel()


def create_app() -> FastAPI:
    settings = load_settings()

    app = FastAPI(
        title="AgentOps",
        version="2.0.0",
        description=(
            "Production-grade AI orchestration backend. "
            "Classify → Plan → Execute → Verify → Respond."
        ),
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ── Middleware (applied in reverse registration order by Starlette) ─────
    # Rate limiting wraps the outermost layer (before auth) so abusive callers
    # are rejected cheaply, before key validation.
    if settings.auth_enabled:
        app.add_middleware(APIKeyMiddleware)

    app.add_middleware(
        RateLimitMiddleware,
        config=RateLimitConfig(requests_per_window=200, window_seconds=60),
    )

    app.include_router(router)
    return app
