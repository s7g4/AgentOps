# Load Testing

`locustfile.py` at the repo root exercises all three entry points against a running instance:

- `POST /messages` — the FSM pipeline, weighted heaviest since it's the highest-traffic path in a real deployment.
- `POST /agents/route` — explicit subtasks (`summary` + `echo`), no decomposer/LLM call, so latency reflects the bus and supervisor, not an upstream provider.
- `POST /workflows` → `POST /workflows/{id}/run` → `DELETE /workflows/{id}` — the full lifecycle for a two-step DAG (`support_pipeline` agent step, then a `refund_policy` tool step chained via `$step.<id>.<key>`).
- `GET /health` — cheap baseline traffic, exempt from rate limiting.

## Running it

```bash
pip install -e ".[loadtest]"
python -m app.main &
locust -f locustfile.py --host http://localhost:8000
```

Open `http://localhost:8089` for the interactive UI, or run headless for a fixed load profile:

```bash
locust -f locustfile.py --host http://localhost:8000 \
    --users 50 --spawn-rate 10 --run-time 2m --headless
```

If the target instance has `AUTH_ENABLED=true`, set `API_KEY` in the environment before starting Locust — the user picks it up in `on_start` and sends it as `X-Api-Key` on every request.

## What to watch

- `GET /metrics` on the target instance during a run — `agentops_request_latency_seconds` and `agentops_tool_execution_latency_seconds` are the numbers that matter, not just Locust's client-side timings.
- With `RATE_LIMIT_BACKEND=memory` (the default), the limiter is per-process — a single instance under load will start returning `429`s once the configured window fills. That's expected and by design, not a bug the load test is meant to uncover; switch to `RATE_LIMIT_BACKEND=redis` if you're load-testing more than one replica and want a shared limit.
- Workflow and routing runs each write to the trace/workflow/routing store on every request — with the `memory` backend this is bounded by the in-process LRU caps; with `TRACE_BACKEND=redis`, watch Redis memory and eviction, not just app CPU.
