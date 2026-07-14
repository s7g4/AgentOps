# Changelog

All notable changes to this project are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.0.0]

The three orchestration systems built in 0.x (FSM pipeline, workflow engine, agent bus) are now one substrate instead of three silos, and the gaps a production deployment would actually hit — untested Redis persistence, single-key auth, a rate limiter that only works on one replica, no client — are closed.

### Added

- `PipelineAgent` wraps the FSM pipeline as a `RoutableAgent`, registered as `support_pipeline` — reachable from a workflow agent-step or a supervisor subtask, not just `POST /messages`.
- `WorkflowStep.kind`: `"tool"` (unchanged) or `"agent"`, dispatching through the same `AgentBus` the supervisor uses. Both kinds produce the same `StepResult` shape, so output-chaining (`$step.<id>.<key>`) works across either.
- Multi-key API auth (`API_KEYS`, comma-separated), replacing the single static `API_KEY`. Every configured key is checked with `hmac.compare_digest`; auth success/failure now logs.
- `RedisRateLimiter` (`RATE_LIMIT_BACKEND=redis`) — a shared fixed-window counter, so every replica behind the same host agrees on the limit instead of each enforcing its own.
- Background workflow execution: `POST /workflows/{id}/run` with `"background": true` returns a `PENDING` execution immediately and runs it via an in-process `asyncio.create_task`; poll `GET .../runs/{execution_id}` for the result.
- `agentops-client` — an installable Python client (sync + async) and `agentops` CLI covering every endpoint, under `client/`.
- Real Redis CI: a `redis:7-alpine` service container in GitHub Actions, plus test coverage for `RedisTraceStore`, `RedisWorkflowStore`, and `RedisRoutingStore` that previously only constructed these classes without exercising them.
- `CONTRIBUTING.md`, issue templates, PR template, `examples/`.
- `TRUST_PROXY_HEADERS` setting (default `false`): gates whether the rate limiter and auth-rejection logging honor `X-Forwarded-For`. When enabled, the *last* hop is used instead of the first.
- `mkdocs.yml` and a full `docs/` site (mkdocs-material) covering architecture, API reference, observability, deployment, load testing, and design decisions.
- `locustfile.py` load-testing `/messages`, `/workflows/{id}/run`, and `/agents/route`.
- `project.urls` in `pyproject.toml` (homepage, repository, issues, changelog).

### Changed

- `README.md` and `docs/architecture.md` rewritten to document the workflow engine and agent bus, which existed in code since 0.x but were never documented.
- Redis client `close()` calls updated to `aclose()` (redis-py 5+ deprecation).

### Removed

- `types-redis` dev dependency — redis-py ships its own inline types (PEP 561) as of the version this project depends on; the external stub package was stale and shadowing them.
- Dead synchronous accessor methods on `TraceStore` (`put_sync`/`get_sync`/etc.) left over from the pre-async runtime, unused since the async migration.

### Fixed

- A test-isolation bug where `Settings()` constructed without an explicit `redis_url` would silently inherit `REDIS_URL` from the environment, causing intermittent failures once CI started setting that variable for the Redis-backed tests.
- Rate-limit and auth-log client-IP resolution no longer trusts `X-Forwarded-For` by default — the header is client-supplied, and trusting it unconditionally let a caller reset their own rate-limit bucket by sending a fresh spoofed value on every request.
- `/docs`, `/redoc`, and `/openapi.json` now require auth when `AUTH_ENABLED=true` (previously excluded alongside `/health`/`/metrics` with no stated rationale).
- `POST /agents/route` and `POST /workflows/{id}/run` no longer leak raw internal exception text (`str(exc)`) in the `500` response body; the exception is logged server-side and a generic message is returned instead.
- `docker-compose.yml` now hardcodes `TRACE_BACKEND`/`RATE_LIMIT_BACKEND` to `redis` instead of `${VAR:-redis}`. Docker Compose substitutes those from the host's `.env` file, and `.env.example` — which the README/DEPLOYMENT.md quickstart tells you to `cp` before `docker compose up` — sets both to `memory`, so traces and rate limits silently did not survive an app-container restart as documented. Verified end to end after the fix.
- Broken relative links in `SECURITY.md` and `DEPLOYMENT.md` that only resolved correctly on GitHub's blob-URL view, not when included into the mkdocs site.

## [0.5.0] — Goal decomposition and routing history

- `DecompositionProvider`: deterministic keyword-based and OpenAI-backed goal decomposition, so `POST /agents/route` can generate subtasks from a plain-language goal instead of requiring them explicit.
- Routing history persistence (`RoutingStoreProtocol`, in-memory and Redis) and `GET /agents/routes`, `GET /agents/routes/{id}`.
- Workflow step output chaining: `$step.<id>.<key>` template resolution against upstream `StepResult.output`.

## [0.4.0] — Multi-agent bus

- `RoutableAgent` ABC, `AgentRegistry`, `AgentBus` — an async in-process message bus for request/reply dispatch between named agents.
- `SupervisorAgent`: concurrent subtask dispatch via `asyncio.gather`, with per-subtask success/failure isolation and an aggregate `completed`/`partial`/`failed` status.
- Built-in reference agents (`echo`, `summary`) and `GET /agents`, `POST /agents/route`.

## [0.3.0] — Workflow engine

- `WorkflowDefinition`/`WorkflowStep`: a validated DAG (duplicate-ID, dangling-dependency, and cycle checks via Kahn's algorithm) at creation time, not at run time.
- `AsyncWorkflowExecutor`: topological-layer execution, each layer run concurrently via `asyncio.gather`, checkpointed to the store after every layer.
- In-memory and Redis-backed workflow stores; full CRUD + run API.
- OpenTelemetry integration: opt-in OTLP export with a no-op tracer shim when disabled, spans per pipeline stage.

## [0.2.0] — Async runtime, ops hardening

- Migrated the FSM runtime from synchronous to `async def`, so a slow LLM call no longer blocks every other in-flight request; concurrent tool execution via `asyncio.gather`.
- `APIKeyMiddleware` (single static key) and sliding-window `RateLimitMiddleware`.
- Multi-stage Dockerfile (non-root user, healthcheck) and GitHub Actions CI (lint, type check, test, Docker smoke test).
- `POST /evaluation` — offline evaluation harness against synthetic ticket data.

## [0.1.0] — Initial FSM pipeline

- Core FSM runtime: `RECEIVED → CLASSIFIED → PLANNING → TOOL_EXECUTION → VERIFYING → COMPLETED`, with `VALID_TRANSITIONS` enforcement.
- `ClassifierAgent`, `PlannerAgent`, `VerifierAgent`, `ResponseGeneratorAgent`, each behind a provider ABC with a deterministic default implementation.
- `ToolRegistry` and two example tools (`CheckOrderStatusTool`, `RefundPolicyTool`).
- `TraceStore` (in-memory, LRU-capped), Prometheus metrics, structured JSON logging with `trace_id` correlation.
- `POST /messages`, `POST /messages/batch`, `GET /trace/{trace_id}`, `GET /trace/`, `GET /tools`.
