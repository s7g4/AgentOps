from __future__ import annotations

from functools import lru_cache

from app.agents.classifier.classifier_agent import ClassifierAgent
from app.agents.planner.planner_agent import PlannerAgent
from app.agents.response_generator.response_generator_agent import ResponseGeneratorAgent
from app.agents.verifier.verifier_agent import VerifierAgent
from app.config.settings import load_settings
from app.logging.structured_logger import configure_structlog
from app.registry.tool_registry import ToolRegistry
from app.runtime.runtime import AgentOpsRuntime
from app.runtime.trace_store import RedisTraceStore, TraceStore

_settings = load_settings()
configure_structlog(log_level=_settings.log_level)


@lru_cache(maxsize=1)
def get_tool_registry() -> ToolRegistry:
    return ToolRegistry.default()


@lru_cache(maxsize=1)
def get_trace_store() -> TraceStore | RedisTraceStore:
    """Return the configured trace store.

    Selects the backend based on ``TRACE_BACKEND`` setting:
      • ``memory`` → in-process TraceStore (default, for tests and local dev)
      • ``redis``  → RedisTraceStore (requires REDIS_URL)
    """
    settings = load_settings()
    if settings.trace_backend == "redis" and settings.redis_url:
        return RedisTraceStore(redis_url=settings.redis_url)
    return TraceStore.default()


@lru_cache(maxsize=1)
def get_runtime() -> AgentOpsRuntime:
    return AgentOpsRuntime(
        classifier=ClassifierAgent(),
        planner=PlannerAgent(),
        verifier=VerifierAgent(),
        responder=ResponseGeneratorAgent(),
        tool_registry=get_tool_registry(),
        trace_store=get_trace_store(),  # type: ignore[arg-type]
    )
