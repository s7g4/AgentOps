"""Deep health check endpoint.

A shallow health check (just ``{"status": "ok"}``) is only useful for
liveness probes.  A deep health check exposes the status of every
dependency so that:

• Kubernetes readiness probes can stop sending traffic to degraded pods.
• On-call engineers see at a glance which dependency is causing the problem
  without needing to SSH into a container.
• Monitoring systems can alert on partial degradation before full outage.

Response shape
──────────────
{
  "status": "ok" | "degraded" | "down",
  "version": "1.0.0",
  "checks": {
    "redis":    "ok" | "error" | "not_configured",
    "openai":   "configured" | "not_configured",
  }
}

HTTP status codes:
  200 → ok or degraded (service is running, some deps may be unavailable)
  503 → down (service cannot function)
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app import __version__
from app.config.settings import load_settings

health_router = APIRouter(tags=["health"])


@health_router.get("/health", summary="Deep health check")
async def health() -> JSONResponse:
    settings = load_settings()
    checks: dict[str, str] = {}
    overall = "ok"

    # ── Redis check ────────────────────────────────────────────────────────
    if settings.redis_url:
        try:
            import redis.asyncio as aioredis  # noqa: PLC0415

            r = aioredis.from_url(settings.redis_url, socket_connect_timeout=2)
            await r.ping()
            await r.aclose()
            checks["redis"] = "ok"
        except Exception:  # noqa: BLE001
            checks["redis"] = "error"
            overall = "degraded"
    else:
        checks["redis"] = "not_configured"

    # ── OpenAI check ───────────────────────────────────────────────────────
    checks["openai"] = "configured" if settings.openai_api_key else "not_configured"

    status_code = 503 if overall == "down" else 200
    return JSONResponse(
        status_code=status_code,
        content={"status": overall, "version": __version__, "checks": checks},
    )
