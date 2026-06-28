# AgentOps Architecture

## Overview

AgentOps is a multi-agent AI orchestration backend built on FastAPI. The core abstraction is a finite state machine (FSM) runtime that drives a deterministic pipeline through four agent stages: classify → plan → execute tools → verify.

---

## Component Map

```
app/
├── api/                   # HTTP transport layer
│   ├── main.py            # FastAPI app factory (create_app)
│   ├── routes.py          # Router aggregation
│   ├── deps.py            # Dependency injection (lru_cache singletons)
│   └── endpoints/
│       ├── messages.py    # POST /messages, POST /messages/batch
│       ├── trace.py       # GET /trace/{trace_id}
│       ├── metrics.py     # GET /metrics (Prometheus)
│       ├── health.py      # GET /health
│       ├── tools.py       # GET /tools
│       └── evaluation.py  # POST /evaluation
│
├── agents/                # Agent layer — stateless, provider-injected
│   ├── classifier/        # ClassifierAgent → ClassificationProvider
│   ├── planner/           # PlannerAgent → PlanningProvider
│   ├── verifier/          # VerifierAgent → VerificationProvider
│   └── response_generator/ # ResponseGeneratorAgent → ResponseProvider
│
├── providers/
│   └── base.py            # 4 ABC interfaces (ClassificationProvider, etc.)
│
├── runtime/
│   ├── runtime.py         # AgentOpsRuntime — FSM orchestrator
│   ├── state_machine.py   # RuntimeState enum + VALID_TRANSITIONS + validate_transition()
│   ├── trace_store.py     # Thread-safe in-memory trace store with eviction cap
│   └── metrics.py         # Prometheus Counter/Histogram definitions
│
├── registry/
│   └── tool_registry.py   # ToolRegistry — register/execute pattern
│
├── tools/
│   ├── base.py            # BaseTool[I, O] ABC
│   └── example_tools.py   # CheckOrderStatusTool, RefundPolicyTool
│
├── schemas/
│   ├── messages.py        # Pydantic v2 request/response models
│   ├── trace.py           # Trace, TraceEvent, ToolCall, AgentDecision
│   ├── classification.py  # Classification
│   ├── plan.py            # ToolPlan
│   └── verification.py    # VerificationResult
│
├── config/
│   └── settings.py        # pydantic-settings BaseSettings (fail-fast validation)
│
├── logging/
│   └── structured_logger.py # structlog JSON output + ContextVar trace_id injection
│
└── evaluation/
    ├── evaluator.py        # Evaluation harness (accuracy, latency, escalation rate)
    └── fake_data.py        # Synthetic ticket generator
```

---

## Request Lifecycle

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

Every state transition is validated by `validate_transition(from_state, to_state)`.
Invalid transitions raise `InvalidTransitionError` immediately.

---

## State Machine

```
                    ┌─────────────────────────────────────────┐
                    │              FAILED                      │
                    └──────────────────────────────────────────┘
                    ▲  ▲  ▲  ▲  ▲  (from any non-terminal state)

RECEIVED → CLASSIFIED → PLANNING → TOOL_EXECUTION → VERIFYING → COMPLETED
```

Legal transitions are declared in `VALID_TRANSITIONS: dict[RuntimeState, frozenset[RuntimeState]]`.

---

## Provider Pattern

Each agent depends on an abstract provider interface, not a concrete implementation:

```python
class ClassifierAgent:
    def __init__(self, provider: ClassificationProvider | None = None):
        self.provider = provider or DeterministicClassifierProvider()
```

To wire in OpenAI (V2):
```python
ClassifierAgent(provider=OpenAIClassificationProvider(client=openai_client))
```

This follows the Open/Closed principle: new providers extend, not modify, the agent.

---

## Observability

### Prometheus Metrics
Exposed at `GET /metrics` in text exposition format.

| Metric | Type | Labels |
|---|---|---|
| `agentops_requests_total` | Counter | `route`, `status` |
| `agentops_request_latency_seconds` | Histogram | `route` |
| `agentops_tool_execution_total` | Counter | `tool_name`, `status` |
| `agentops_tool_execution_latency_seconds` | Histogram | `tool_name` |
| `agentops_verifier_escalations_total` | Counter | — |

### Structured Logging
Every log line is a JSON object:
```json
{
  "timestamp": "2026-07-02T16:00:00.000Z",
  "level": "info",
  "event": "request_received",
  "trace_id": "550e8400-e29b-...",
  "customer_id": "cust_123",
  "filename": "runtime.py"
}
```

`trace_id` is injected automatically via `contextvars.ContextVar` — no manual passing required.

### Execution Traces
Every request produces a structured `Trace` stored in `TraceStore`:
```json
{
  "trace_id": "...",
  "timeline": [
    {"name": "state:received", "timestamp": "...", "data": {...}},
    {"name": "state:classified", ...},
    {"name": "tool_execution", "data": {"tool_name": "refund_policy", "status": "success", "duration_ms": 0.5}},
    {"name": "verification_summary", ...},
    {"name": "state:completed", ...}
  ],
  "tool_calls": [...],
  "agent_decisions": [...],
  "final_response": {...}
}
```

---

## Dependency Injection

Singletons are created via `functools.lru_cache` in `app/api/deps.py`:

```python
@lru_cache(maxsize=1)
def get_runtime() -> AgentOpsRuntime: ...

@lru_cache(maxsize=1)
def get_trace_store() -> TraceStore: ...
```

These are bound to `app.state` at startup for direct access in tests.
`override_settings()` in `app/config/settings.py` allows test isolation.

---

## Versioned Roadmap

| Version | Core Addition |
|---|---|
| **V1** | FSM Runtime, 4 agents, tool registry, metrics, evaluation |
| **V2** | OpenAI LLM providers, async handlers, Redis TraceStore, auth middleware |
| **V3** | DAG workflow engine (steps, fan-out, conditional branches, retries) |
| **V4** | Multi-agent messaging, supervisor pattern, agent registry |
| **V5** | Multi-tenancy, RBAC, audit log, SLA enforcement, plugin system |
