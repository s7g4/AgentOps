# API Reference

## Error responses

Every error response — 401s and 429s from middleware, 404/422/500s raised anywhere in `app/api/endpoints/` — has the same shape:

```json
{ "error": "Not Found", "detail": "Trace 'abc123' not found" }
```

`error` is the standard HTTP reason phrase for the status code; `detail` is the specific message. Client code should read `detail` for the message and can use `error` as a stable, status-code-derived category if useful.

## `POST /messages` / `POST /messages/batch`

Runs a message through the FSM pipeline. `batch` processes all messages concurrently.

```json
// Request
{ "source": "ticket", "customer_id": "cust_123", "message": "I want a refund" }

// Response
{ "trace_id": "550e8400-...", "intent": "refund", "confidence": 0.8, "escalated": false, "response": "..." }
```

## Workflows

| Route | Description |
|---|---|
| `POST /workflows` | Create a workflow definition. Validates the DAG (cycles, dangling deps) at creation, not at run time. |
| `GET /workflows` | Paginated list of definitions. |
| `GET /workflows/{id}` | Fetch one definition. |
| `DELETE /workflows/{id}` | Delete a definition. |
| `POST /workflows/{id}/run` | Execute. Blocks until completion by default; pass `"background": true` to get a `pending` execution back immediately and poll for the result. |
| `GET /workflows/{id}/runs` | Paginated execution history. |
| `GET /workflows/{id}/runs/{execution_id}` | Fetch one execution's status and step results. |

Each step is `"kind": "tool"` (dispatches to the tool registry) or `"kind": "agent"` (dispatches to the agent bus). Steps in the same DAG layer run concurrently via `asyncio.gather`; a step can reference an upstream step's output with `"$step.<id>.<key>"`.

**No idempotency-key support.** `POST /workflows/{id}/run` has no `Idempotency-Key` header or equivalent deduplication — if a client retries after a timeout, the workflow runs again. This matters most for non-idempotent tool steps (anything with a real side effect, not the bundled example tools). If you need retry-safety here, build it at the call site today (e.g., check `GET /workflows/{id}/runs` for an existing in-flight/completed execution before retrying) — it isn't handled server-side yet.

## Agents

| Route | Description |
|---|---|
| `GET /agents` | List registered agents (name + description). |
| `POST /agents/route` | Dispatch a goal. Supply `subtasks` explicitly, or omit them to use the configured decomposer (OpenAI if `OPENAI_API_KEY` is set, otherwise a deterministic keyword matcher). |
| `GET /agents/routes` | Paginated routing history. |
| `GET /agents/routes/{routing_id}` | Fetch one routing run. |

`RoutingResult.status` is `completed` (all subtasks succeeded), `partial` (mixed), or `failed` (all failed) — one subtask failing never cancels the others. Same idempotency caveat as workflows above: a retried `POST /agents/route` re-dispatches every subtask.

**No per-key data isolation.** Any valid API key can read every trace, workflow, and routing record in the deployment, regardless of which key created them. See `docs/architecture.md`'s Authentication section if this matters for your deployment.

## Observability & ops

| Route | Description |
|---|---|
| `GET /trace/{trace_id}` | Full execution timeline for a `/messages` request — state transitions, tool calls, agent decisions. |
| `GET /trace/` | Paginated trace listing. |
| `GET /metrics` | Prometheus exposition format. |
| `GET /health` | Liveness + dependency readiness (`redis`, `openai`). |
| `GET /tools` | Registered tool names and input schemas. |
| `POST /evaluation` | Runs the evaluation harness on synthetic ticket data. |

Interactive, always-current API docs (OpenAPI/Swagger) are served at `/docs` on a running instance:

![Swagger UI listing all endpoints](assets/swagger-overview.png)

![Swagger UI Try-it-out panel for POST /messages](assets/swagger-messages-expanded.png)
