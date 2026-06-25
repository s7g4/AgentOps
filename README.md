# AgentOps

A reference-quality, production-grade orchestrator demonstrating structured task routing, concurrent tool execution, observability, and evaluation.

[![CI](https://github.com/your-org/agentops/actions/workflows/ci.yml/badge.svg)](https://github.com/your-org/agentops/actions)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/release/python-3120/)
[![Coverage: 96%](https://img.shields.io/badge/coverage-96%25-brightgreen.svg)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Core System Architecture

```mermaid
graph TD
    Client[HTTP Client] -->|POST /messages| API[FastAPI API Layer]
    Client -->|GET /trace/{id}| API
    Client -->|GET /metrics| API
    
    subgraph API_Layer [API Transport]
        API
        Auth[APIKeyMiddleware] --> API
        RateLimit[RateLimitMiddleware] --> Auth
    end

    API -->|invoke| Runtime[AgentOpsRuntime]
    
    subgraph Runtime_FSM [Orchestrator FSM Engine]
        Runtime
        State[RuntimeState Validation FSM] <--> Runtime
    end

    Runtime -->|1. Classify| Classifier[ClassifierAgent]
    Runtime -->|2. Plan| Planner[PlannerAgent]
    Runtime -->|3. Parallel Exec| Executor[Tool Execution Wrapper]
    Runtime -->|4. Verify| Verifier[VerifierAgent]
    Runtime -->|5. Respond| Responder[ResponseGeneratorAgent]

    subgraph Agents [Stateless Agent Layer]
        Classifier -->|ABC| ClassProvider[ClassificationProvider]
        Planner -->|ABC| PlanProvider[PlanningProvider]
        Verifier -->|ABC| VerifyProvider[VerificationProvider]
        Responder -->|ABC| RespProvider[ResponseProvider]
    end

    subgraph Tools [Tool Registry Layer]
        Executor -->|lookup| Registry[ToolRegistry]
        Registry -->|validate & execute| CoreTools[Core Tools]
    end

    Runtime -->|Write timeline & outcomes| Store[TraceStore / RedisTraceStore]
    Runtime -->|Observe latencies & state changes| Prometheus[Prometheus Client Metrics]
```

See [docs/architecture.md](docs/architecture.md) for full component details.

---

## Quickstart

### Prerequisites
- Python 3.12+
- Docker (optional)

### Local Development

```bash
# Clone
git clone https://github.com/your-org/agentops.git
cd agentops

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies and package
pip install -e .

# Run application
python -m app.main
```

The API is available at `http://localhost:8000`.

### Docker

```bash
docker compose up
```

### Environment Configuration

| Variable | Default | Description |
|---|---|---|
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `8000` | Listen port |
| `LOG_LEVEL` | `INFO` | `DEBUG`/`INFO`/`WARNING`/`ERROR` |
| `OPENAI_API_KEY` | — | Required for upstream LLM execution |
| `REDIS_URL` | — | Enables Redis-backed persistence |
| `TRACE_BACKEND` | `memory` | `memory` or `redis` |
| `AUTH_ENABLED` | `false` | Enable API key header validation |
| `API_KEY` | — | Target verification value when auth is enabled |

---

## API Reference

### `POST /messages`
Processes a message payload through the orchestrated pipeline.

**Request**
```json
{
  "source": "ticket",
  "customer_id": "cust_123",
  "message": "I want a refund for my order"
}
```

**Response**
```json
{
  "trace_id": "550e8400-...",
  "intent": "refund",
  "confidence": 0.8,
  "escalated": false,
  "response": "Refund policy: Refunds accepted within 30 days..."
}
```

### `POST /messages/batch`
Executes concurrent batch validation for multiple ticket entries.

### `GET /trace/{trace_id}`
Retrieves a detailed transaction timeline, including step execution sequences and internal decisions.

### `GET /metrics`
Exposes system indicators in Prometheus exposition format.

### `GET /health`
Liveness and deep readiness verification probe.

### `GET /tools`
Lists active registry tools and metadata.

### `POST /evaluation`
Runs automated validation metrics on structured testing inputs.

---

## Verification & Testing

```bash
# Run test suite
pytest -q

# Run with test coverage metrics
pytest --cov=app --cov-report=term-missing
```

---

## System Design Guarantees

- **Provider Abstraction**: Decoupled agent behavior from external dependency libraries. All language processors consume abstract base classes.
- **FSM State Safety**: Transitions enforce state progress via strict state transitions. Any unauthorized change calls fail fast.
- **Structured Observability**: Logs compile to flat-dictionary JSON structures. Context tracking is preserved across async runtime calls via local contextvars.
- **Config Initialization Safety**: App configuration parses explicitly at startup utilizing schema models; the application panics immediately on invalid or missing configurations.
- **Eviction-capped Storage**: Local in-memory trace indexing enforces strict storage bounds (10,000 trace ceiling) using LRU-eviction locks.
