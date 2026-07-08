# Design Decisions: One Substrate, Three Entry Points

Most agent frameworks make you choose a shape up front — a chat loop, a DAG, a swarm — and then bend every use case to fit it. AgentOps started from a different premise: the shape of the *request* should decide how it's handled, not the framework. That premise only holds together if all three shapes are backed by the same execution substrate. This is the reasoning behind that decision, and what it cost to make it hold.

## The three shapes are real, not decorative

- **`POST /messages`** is for work whose steps never change: classify → plan → execute tools → verify → respond, every time, only the content varies. This is naturally a state machine, not a chat loop — an explicit `RuntimeState` enum with a `VALID_TRANSITIONS` table (`app/runtime/state_machine.py`) that raises immediately on an illegal move, rather than a prompt that's supposed to keep the model on-script.
- **`POST /workflows/{id}/run`** is for work whose *shape* is known ahead of time but whose steps have real dependencies — fetch order, then refund, then notify. That's a DAG, and DAGs have a property FSMs and chat loops don't: you can validate them statically. `WorkflowDefinition` rejects cycles and dangling dependencies at `POST /workflows` time (Kahn's algorithm), not three steps into a run.
- **`POST /agents/route`** is for work whose shape isn't known until the goal is — a goal gets decomposed into subtasks and dispatched to named agents. This is the only one of the three that benefits from an LLM in the loop, and even that's optional: `DecompositionProvider` falls back to a deterministic keyword matcher with no API key, so the routing behavior itself is testable without one.

Building three different products would have been the easy way to ship this. It would also have meant three copies of tool execution, three copies of error handling, three copies of persistence — and a support ticket handled through the FSM pipeline would have been unreachable from a workflow, even though "run a full support turn as one step in a bigger process" is an obvious, real need.

## The seam: agents are the common currency

The thing that makes one substrate possible is `RoutableAgent` — a small ABC with one method, `handle(message) -> reply`. Every agent reachable from `/agents/route` — `echo`, `summary`, and critically, `support_pipeline` — is addressable through `AgentBus.send()`. `PipelineAgent` (`app/agents/pipeline_agent.py`) wraps the *entire* FSM runtime behind that interface. So a workflow step with `"kind": "agent", "agent_name": "support_pipeline"` runs the exact same classify→plan→execute→verify→respond sequence that backs `/messages` — not a reimplementation, not a call-out, the same runtime instance wired through dependency injection (`get_agent_registry()` registers `PipelineAgent(get_runtime())`, not a fresh one).

That's the difference between three entry points and three products. A workflow step and a routed subtask both go through `AgentBus.send()`; the workflow executor's tool-kind steps and the FSM pipeline's tool calls both go through `ToolRegistry.execute()`. There's one dispatch path per capability, reused from three directions.

## Tradeoffs that fell out of this shape

**DAG validation at write time, not run time.** Rejecting a cyclic or dangling-dependency workflow at `POST /workflows` costs an extra pass over the step list on creation. The alternative — discovering it mid-run, with some steps already executed and side effects already fired — is strictly worse, so this wasn't a close call.

**In-process background execution, no durable queue.** `POST /workflows/{id}/run` with `"background": true` hands the execution to `asyncio.create_task()` and persists it as `PENDING` immediately. A run in flight is lost on process restart. For a single-container deployment this is the right tradeoff — a durable queue (Celery, an actual task broker) is real operational weight for a problem that doesn't exist yet. The moment horizontal scaling matters, this is the documented, obvious upgrade path — not a rewrite.

**Sliding window in memory, fixed window in Redis, not the same algorithm twice.** The in-memory rate limiter is a per-process sliding window (accurate, no cross-request coordination needed). The Redis-backed one is a fixed-window `INCR`+`EXPIRE` — a real approximation that allows up to 2× burst at a window boundary, in exchange for one round trip instead of a Lua script and agreement across every replica. Reimplementing sliding-window semantics in Redis was available and explicitly not worth it: the imprecision is bounded and understood, and buys meaningfully simpler code.

**Provider ABCs everywhere, not just for the LLM calls.** `ClassificationProvider`, `DecompositionProvider`, and friends exist so that swapping `DeterministicClassifierProvider` for `OpenAIClassificationProvider` touches one injection site, not the agent's internals. This is what keeps the whole system testable without an API key — every deterministic provider is a real, exercised code path in CI, not a mock standing in for behavior nobody's checked.

## Hardening in practice

A later security pass on this codebase found a real instance of the rate limiter and the auth middleware's rejection logging both keying off `X-Forwarded-For` unconditionally. That header is client-supplied, so trusting it by default meant a caller could reset their own rate-limit bucket by sending a fresh spoofed value on every request — it defeats the point of rate limiting on any deployment that isn't sitting behind a reverse proxy overwriting the header. The fix: a `trust_proxy_headers` setting, off by default, falling back to the actual socket peer address unless a deployment explicitly opts in, and even then reading the *last* hop rather than the client-controlled first one. Same instinct as the DAG-validation call above — fail toward the safe, boring default, and make the riskier behavior something you have to ask for.
