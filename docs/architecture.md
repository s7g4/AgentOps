# AgentOps Architecture

## Overview

AgentOps is a multi-agent orchestration backend built on FastAPI. There are three orchestration entry points, all sharing one agent substrate:

1. **FSM pipeline** (`POST /messages`) — a fixed classify → plan → execute tools → verify → respond sequence, enforced by an explicit state machine.
2. **Workflow engine** (`POST /workflows/{id}/run`) — a validated DAG of steps, executed in parallel layers.
3. **Agent bus + supervisor** (`POST /agents/route`) — a goal decomposed into subtasks dispatched concurrently to named agents.

The FSM pipeline is itself reachable as an agent (`support_pipeline`), and workflow steps can target either a tool or an agent. That's the seam that ties the three together: a workflow can run a full support ticket through the FSM pipeline as one node in a larger graph, and a routed goal can land on the same pipeline via the bus.

---

## Component Map

```
app/
├── api/                    # HTTP transport layer
│   ├── main.py             # FastAPI app factory (create_app), lifespan startup/shutdown
│   ├── routes.py           # Router aggregation
│   ├── deps.py             # Dependency injection (lru_cache singletons)
│   └── endpoints/
│       ├── messages.py     # POST /messages, POST /messages/batch
│       ├── workflows.py    # Workflow CRUD + run (sync or background) + run history
│       ├── agents.py       # GET /agents, POST /agents/route, routing history
│       ├── trace.py        # GET /trace/{trace_id}, GET /trace/
│       ├── metrics.py      # GET /metrics (Prometheus)
│       ├── health.py       # GET /health (deep dependency check)
│       ├── tools.py        # GET /tools
│       └── evaluation.py   # POST /evaluation
│
├── runtime/                 # FSM pipeline orchestrator
│   ├── runtime.py           # AgentOpsRuntime — async FSM orchestrator
│   ├── state_machine.py     # RuntimeState enum + VALID_TRANSITIONS + validate_transition()
│   ├── trace_store.py       # TraceStore (in-memory) / RedisTraceStore
│   └── metrics.py           # Prometheus Counter/Histogram definitions
│
├── agents/                  # Agent layer
│   ├── classifier/, planner/, verifier/, response_generator/  # FSM pipeline stages
│   ├── base.py               # RoutableAgent ABC — bus-addressable agents
│   ├── registry.py            # AgentRegistry — name → RoutableAgent
│   ├── pipeline_agent.py        # PipelineAgent — wraps AgentOpsRuntime as a RoutableAgent
│   └── builtin/                # EchoAgent, SummaryAgent — reference implementations
│
├── messaging/                # Multi-agent routing
│   ├── message.py              # AgentMessage, SubTask, SubTaskResult, RoutingResult
│   ├── bus.py                  # AgentBus — resolves a recipient and awaits its handle()
│   ├── supervisor.py           # SupervisorAgent — concurrent subtask dispatch + aggregation
│   ├── decomposition.py         # DecompositionProvider — goal → subtasks (deterministic or OpenAI)
│   └── routing_store.py         # Routing history: in-memory / Redis
│
├── workflows/                # DAG workflow engine
│   ├── definition.py            # WorkflowDefinition, WorkflowStep (kind="tool"|"agent"), validation
│   ├── execution.py              # WorkflowExecution, StepResult, status enums
│   ├── executor.py                # AsyncWorkflowExecutor — topological layers + asyncio.gather
│   ├── template.py                 # $step.<id>.<key> output-chaining resolution
│   └── store.py                     # Definitions + executions: in-memory / Redis
│
├── providers/
│   ├── base.py               # Sync + async ABC interfaces per pipeline stage
│   └── openai_providers.py    # OpenAI-backed implementations (classify, plan, verify, respond)
│
├── registry/
│   └── tool_registry.py       # ToolRegistry — register/execute pattern
│
├── tools/
│   ├── base.py                 # BaseTool[I, O] ABC
│   └── example_tools.py         # CheckOrderStatusTool, RefundPolicyTool
│
├── middleware/
│   ├── auth.py                  # APIKeyMiddleware — multi-key, constant-time comparison
│   └── rate_limit.py              # RateLimitMiddleware — in-memory sliding window / Redis fixed window
│
├── schemas/                  # Pydantic v2 request/response models (API boundary only)
├── config/settings.py         # pydantic-settings BaseSettings (fail-fast validation)
├── logging/structured_logger.py # structlog JSON output + ContextVar trace_id injection
├── telemetry/                  # OpenTelemetry — opt-in OTLP export, no-op when disabled
└── evaluation/                  # Offline evaluation harness against synthetic tickets
```

---

## FSM Pipeline: Request Lifecycle

```
POST /messages
     │
     ▼
deps.get_runtime() → AgentOpsRuntime (singleton)
     │
     ▼
handle_message(req: MessageRequest)
     │
     ├─ bind trace_id to ContextVar (all log lines carry it)
     │
     ├─ RECEIVED   → record initial state event
     ├─ CLASSIFIED → classifier.classify(message)
     ├─ PLANNING   → planner.plan(intent, message)
     ├─ TOOL_EXEC  → for each tool call: registry.execute() with tenacity retry
     ├─ VERIFYING  → verifier.verify(intent, tool_outputs, message)
     ├─ COMPLETED  → responder.generate() + trace_store.put(trace)
     │
     └─ FAILED (on any exception) → trace_store.put(trace) + safe error response
```

Every state transition is validated by `validate_transition(from_state, to_state)`. Invalid transitions raise `InvalidTransitionError` immediately.

```
                    ┌─────────────────────────────────────────┐
                    │              FAILED                      │
                    └──────────────────────────────────────────┘
                    ▲  ▲  ▲  ▲  ▲  (from any non-terminal state)

RECEIVED → CLASSIFIED → PLANNING → TOOL_EXECUTION → VERIFYING → COMPLETED
```

`PipelineAgent` (`app/agents/pipeline_agent.py`) wraps this entire lifecycle behind the `RoutableAgent` interface, registered as `support_pipeline`, so it's reachable from a workflow agent-step or a supervisor subtask with no special casing at the call site.

---

## Workflow Engine: Execution Model

1. `WorkflowDefinition.execution_layers()` topologically sorts steps via Kahn's algorithm into layers — each layer's steps have all dependencies satisfied by earlier layers.
2. `AsyncWorkflowExecutor.run()` executes one layer at a time: `asyncio.gather()` over every step in the layer, checkpointing the execution to the store after each layer completes.
3. A step is `kind="tool"` (runs via `ToolRegistry.execute()`, wrapped in `asyncio.to_thread()` since example tools are synchronous) or `kind="agent"` (runs via `AgentBus.send()`, awaited directly since `RoutableAgent.handle()` is already a coroutine). Both produce the same `StepResult` shape.
4. If any step in a layer fails, all not-yet-executed steps are marked `SKIPPED` and the execution transitions to `FAILED`. One failure does not stop steps already dispatched in the same layer — they still run to completion via `asyncio.gather(..., return_exceptions=True)`.
5. `static_input` values of the form `"$step.<id>.<key>"` are resolved against upstream `StepResult.output` before a step runs (`app/workflows/template.py`), so a step can consume a prior step's output regardless of whether that step was a tool or an agent.

`POST /workflows/{id}/run` runs synchronously by default. With `"background": true`, the execution is persisted as `PENDING` and handed to an `asyncio.create_task()` immediately; the caller polls `GET .../runs/{execution_id}`. This is in-process only — a run in flight is lost on process restart, which is the right tradeoff for a single-container deployment. A durable queue is the natural upgrade if that stops being true.

---

## Agent Bus & Supervisor: Routing Model

`SupervisorAgent.route(goal, subtasks)`:

- If `subtasks` are supplied explicitly, dispatches exactly those — deterministic, no LLM call, testable without an API key.
- If omitted, calls the configured `DecompositionProvider` (`OpenAIDecompositionProvider` if `OPENAI_API_KEY` is set, otherwise `DeterministicDecompositionProvider`, a keyword matcher) to generate the subtask list.
- Every subtask is dispatched concurrently via `asyncio.gather(..., return_exceptions=True)` — one agent failing never cancels the others.
- `RoutingResult.status` is derived from the aggregate: `completed` (all succeeded), `partial` (mixed), `failed` (all failed or empty).

`AgentBus.send(message, registry)` is the single hop every dispatch goes through: resolve `message.recipient` in `AgentRegistry`, await `agent.handle(message)`, return the reply. Both the supervisor and the workflow executor's agent-kind steps go through this same call.

---

## Provider Pattern

Each pipeline stage depends on an abstract provider interface, not a concrete implementation:

```python
class ClassifierAgent:
    def __init__(self, provider: ClassificationProvider | None = None):
        self.provider = provider or DeterministicClassifierProvider()
```

To wire in OpenAI:

```python
ClassifierAgent(provider=OpenAIClassificationProvider(api_key=settings.openai_api_key))
```

This follows the Open/Closed principle: new providers extend, not modify, the agent. The same pattern applies to goal decomposition (`DecompositionProvider`).

---

## Persistence

Traces, workflow definitions/executions, and routing history each have two implementations behind the same protocol:

- **In-memory** (default) — thread-safe, zero dependencies, correct for a single process and for tests.
- **Redis** (`TRACE_BACKEND=redis`, requires `REDIS_URL`) — persists across restarts, shared across replicas, TTL-based expiry (30 days for executions/routing history, 7 days for traces).

Rate limiting has the same two-tier shape (`RATE_LIMIT_BACKEND=memory|redis`): in-memory is a per-process sliding window; Redis is a shared fixed-window counter (`INCR` + `EXPIRE`), a deliberate approximation that trades sliding-window precision for a single round trip and agreement across every replica.

CI runs a real `redis:7-alpine` service container so all Redis-backed code paths are exercised on every push — not just constructed and left untested.

---

## Observability

### Prometheus Metrics

Exposed at `GET /metrics` in text exposition format.

| Metric                                    | Type      | Labels                |
| ----------------------------------------- | --------- | --------------------- |
| `agentops_requests_total`                 | Counter   | `route`, `status`     |
| `agentops_request_latency_seconds`        | Histogram | `route`               |
| `agentops_tool_execution_total`           | Counter   | `tool_name`, `status` |
| `agentops_tool_execution_latency_seconds` | Histogram | `tool_name`           |
| `agentops_verifier_escalations_total`     | Counter   | —                     |

### Structured Logging

Every log line is a JSON object, with `trace_id` injected automatically via `contextvars.ContextVar` — no manual passing required.

### Tracing

`app/telemetry` wraps OpenTelemetry behind a no-op shim: `get_tracer()` returns a real tracer only when `OTEL_ENABLED=true` and the `[otel]` extras are installed, otherwise every `start_as_current_span()` call is a zero-cost context manager. The FSM pipeline emits one span per stage (classify/plan/execute/verify).

### Execution Traces

Every `/messages` request produces a structured `Trace` in `TraceStore`: state transitions, tool calls, and agent decisions, retrievable via `GET /trace/{trace_id}`.

---

## Authentication

`APIKeyMiddleware` validates the `X-Api-Key` header when `AUTH_ENABLED=true`, against every key in `Settings.valid_api_keys()` (the union of `API_KEYS`, comma-separated, and the legacy single `API_KEY`). Comparison uses `hmac.compare_digest` against every configured key — not just the first — so response timing doesn't leak how many keys exist or which one matched. This is deliberately simpler than JWT/OAuth: there's no session or logged-in user, just a caller presenting a shared secret, so there's no expiry or refresh flow to build or operate.

Only `/health` and `/metrics` bypass auth (liveness probes and scrapers need to run with no credentials). `/docs`, `/redoc`, and `/openapi.json` do **not** bypass it — once auth is enabled, the API schema itself requires a key too.

### Client IP and `X-Forwarded-For`

Both the auth middleware (for the `client` field on rejected-request log lines) and the rate limiter (for the bucket key) need a caller IP. `X-Forwarded-For` is a client-supplied header — trusting it unconditionally lets a caller reset their own rate-limit bucket by sending a fresh spoofed value on every request. It's only honored when `Settings.trust_proxy_headers` is `true`, and even then the *last* entry is used (the hop a well-behaved reverse proxy appends), not the first (the hop a client controls). By default (`trust_proxy_headers=false`), both fall back to `request.client.host`, the actual socket peer address — correct when the app is reachable directly, which is the safe assumption absent an explicit opt-in.

---

## Dependency Injection

Singletons are created via `functools.lru_cache` in `app/api/deps.py` — `get_runtime()`, `get_tool_registry()`, `get_trace_store()`, `get_agent_registry()`, `get_agent_bus()`, `get_supervisor()`, `get_workflow_store()`, `get_workflow_executor()`, `get_routing_store()`, `get_rate_limiter()`. `get_agent_registry()` registers `PipelineAgent(get_runtime())` alongside the built-in demo agents, so the DI-wired runtime singleton — not a fresh one — is what the bus reaches. Every one of these is bound to `app.state` at startup and closed (where a `close()` method exists) on shutdown — see `app/api/main.py`'s lifespan handler.

Note for anyone testing against different backends within one process: these `lru_cache` singletons have no invalidation hook, so switching `TRACE_BACKEND`/`RATE_LIMIT_BACKEND` via `override_settings()` after any of these getters has already been called (e.g. by an earlier test's `create_app()`) has no effect — the cached instance from the first call persists for the life of the process. The Redis-backed store test suites (`test_redis_trace_store.py` etc.) sidestep this by constructing the Redis classes directly rather than going through `app/api/deps.py`.

These are bound to `app.state` at startup for direct access in tests. `override_settings()` in `app/config/settings.py` allows test isolation.
