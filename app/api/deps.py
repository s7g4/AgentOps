from __future__ import annotations

from functools import lru_cache

from app.agents.builtin import EchoAgent, SummaryAgent
from app.agents.classifier.classifier_agent import ClassifierAgent
from app.agents.pipeline_agent import PipelineAgent
from app.agents.planner.planner_agent import PlannerAgent
from app.agents.registry import AgentRegistry
from app.agents.response_generator.response_generator_agent import ResponseGeneratorAgent
from app.agents.verifier.verifier_agent import VerifierAgent
from app.config.settings import load_settings
from app.logging.structured_logger import configure_structlog
from app.messaging.bus import AgentBus
from app.messaging.decomposition import (
    DecompositionProvider,
    DeterministicDecompositionProvider,
    OpenAIDecompositionProvider,
)
from app.messaging.routing_store import (
    InMemoryRoutingStore,
    RedisRoutingStore,
    RoutingStoreProtocol,
)
from app.messaging.supervisor import SupervisorAgent
from app.middleware.rate_limit import InMemoryRateLimiter, RateLimiter, RedisRateLimiter
from app.registry.tool_registry import ToolRegistry
from app.runtime.runtime import AgentOpsRuntime
from app.runtime.trace_store import RedisTraceStore, TraceStore
from app.workflows.executor import AsyncWorkflowExecutor
from app.workflows.store import InMemoryWorkflowStore, RedisWorkflowStore

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
def get_workflow_store() -> InMemoryWorkflowStore | RedisWorkflowStore:
    """Return the configured workflow store.

    Reuses trace_backend — if Redis is configured for traces, workflows
    also use Redis.  No new settings required.
    """
    settings = load_settings()
    if settings.trace_backend == "redis" and settings.redis_url:
        return RedisWorkflowStore(redis_url=settings.redis_url)
    return InMemoryWorkflowStore()


@lru_cache(maxsize=1)
def get_workflow_executor() -> AsyncWorkflowExecutor:
    return AsyncWorkflowExecutor(
        tool_registry=get_tool_registry(),
        store=get_workflow_store(),
        agent_bus=get_agent_bus(),
        agent_registry=get_agent_registry(),
    )


@lru_cache(maxsize=1)
def get_routing_store() -> RoutingStoreProtocol:
    """Return the configured routing store.

    Reuses trace_backend — if Redis is configured for traces, routing history
    also uses Redis.
    """
    settings = load_settings()
    if settings.trace_backend == "redis" and settings.redis_url:
        return RedisRoutingStore(redis_url=settings.redis_url)
    return InMemoryRoutingStore()


@lru_cache(maxsize=1)
def get_decomposition_provider() -> DecompositionProvider:
    """Return the configured decomposition provider.

    Uses OpenAI if the API key is set, otherwise falls back to deterministic.
    """
    settings = load_settings()
    if settings.openai_api_key:
        return OpenAIDecompositionProvider(api_key=settings.openai_api_key)
    return DeterministicDecompositionProvider()


@lru_cache(maxsize=1)
def get_agent_registry() -> AgentRegistry:
    """Return the AgentRegistry pre-loaded with built-in agents.

    Registers the demo agents (echo, summary) plus PipelineAgent, which
    wraps the DI-wired AgentOpsRuntime singleton so the classify/plan/
    execute/verify/respond pipeline is reachable from workflow agent-steps
    and supervisor subtasks under the name "support_pipeline".
    """
    registry = AgentRegistry()
    registry.register(EchoAgent())
    registry.register(SummaryAgent())
    registry.register(PipelineAgent(get_runtime()))
    return registry


@lru_cache(maxsize=1)
def get_agent_bus() -> AgentBus:
    return AgentBus()


@lru_cache(maxsize=1)
def get_supervisor() -> SupervisorAgent:
    return SupervisorAgent(
        bus=get_agent_bus(),
        registry=get_agent_registry(),
        decomposer=get_decomposition_provider(),
        store=get_routing_store(),
    )


@lru_cache(maxsize=1)
def get_rate_limiter() -> RateLimiter:
    """Return the configured rate limiter.

    "memory" is correct for a single process; "redis" shares the counter
    across every replica behind the same host — required the moment more
    than one process answers requests, otherwise each replica enforces its
    own independent limit.
    """
    settings = load_settings()
    if settings.rate_limit_backend == "redis" and settings.redis_url:
        return RedisRateLimiter(redis_url=settings.redis_url)
    return InMemoryRateLimiter()


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

