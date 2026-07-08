# Getting Started

**Requirements**: Python 3.12+, Docker (optional)

```bash
git clone https://github.com/s7g4/AgentOps.git
cd AgentOps
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m app.main
```

API available at `http://localhost:8000`, interactive docs at `/docs`.

## Docker

```bash
cp .env.example .env
docker compose up --build
```

Builds the app, wires it to Redis with a persistent volume, and doesn't expose Redis to the host — verified to survive an app-container restart without losing traces. See [Deployment](deployment.md) for taking this further (Fly.io, Render, or a bare VPS) and the production checklist (auth, Redis, rate-limit backend) to get through before exposing it publicly.

## Client / CLI

A separate installable package wraps the API:

```bash
pip install -e ./client
agentops health
agentops send "I want a refund" --customer-id cust_1
agentops workflows run <workflow-id>
```

See [client/README.md](https://github.com/s7g4/AgentOps/blob/main/client/README.md) for the full command reference, and [examples/](https://github.com/s7g4/AgentOps/tree/main/examples) for three runnable scripts (send a message, run a workflow with an agent step, route a goal).

## Configuration

| Variable | Default | Description |
|---|---|---|
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `8000` | Listen port |
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `OPENAI_API_KEY` | — | Enables LLM-backed providers and goal decomposition |
| `REDIS_URL` | — | Enables Redis-backed persistence and distributed rate limiting |
| `TRACE_BACKEND` | `memory` | `memory` or `redis` — also governs workflow and routing-history storage |
| `RATE_LIMIT_BACKEND` | `memory` | `memory` (per-process) or `redis` (shared across replicas) |
| `AUTH_ENABLED` | `false` | Enable `X-Api-Key` header validation |
| `API_KEYS` | — | Comma-separated list of valid keys |
| `API_KEY` | — | Single-key fallback, folded into `API_KEYS` |
| `OTEL_ENABLED` | `false` | Export spans to an OTLP collector |
| `OTEL_ENDPOINT` | `http://localhost:4317` | OTLP gRPC endpoint |

`memory` backends are correct for a single process. The moment more than one replica sits behind the same host, set `REDIS_URL` and switch `TRACE_BACKEND`/`RATE_LIMIT_BACKEND` to `redis` — otherwise each replica keeps its own traces, workflow state, and rate-limit counters.

## Testing

```bash
pytest -q                                       # full suite (Redis-backed tests skip without a reachable Redis)
REDIS_URL=redis://localhost:6379/0 pytest -q    # include Redis-backed persistence and rate-limit tests
pytest --cov=app --cov-report=term-missing      # with coverage
ruff check .                                    # lint
mypy app                                        # type check
```

CI runs against a real `redis:7-alpine` service container, so the Redis-backed stores and rate limiter get exercised on every push, not just mocked.
