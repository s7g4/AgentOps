# AgentOps

A multi-agent orchestration backend built on FastAPI. Three ways to run work through the same agent substrate: a deterministic FSM pipeline for single-turn requests, a DAG workflow engine for multi-step processes, and a supervisor/bus for dispatching goals across named agents.

[![CI](https://github.com/s7g4/AgentOps/actions/workflows/ci.yml/badge.svg)](https://github.com/s7g4/AgentOps/actions/workflows/ci.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/release/python-3120/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/s7g4/AgentOps/blob/main/LICENSE)

![Terminal walkthrough of the three entry points](assets/demo-terminal.gif)

## Why three entry points

Most agent frameworks pick one shape and force everything through it. AgentOps keeps three, because the request shapes are genuinely different:

- **`POST /messages`** — a single customer message goes through a fixed pipeline (classify → plan → execute tools → verify → respond). Use this when the shape of the work never changes, only the content.
- **`POST /workflows/{id}/run`** — an explicit DAG of steps with dependencies, run in parallel layers. Use this when you know the shape of the process ahead of time (fetch order, then refund, then notify).
- **`POST /agents/route`** — a goal gets decomposed (by an LLM or deterministically) into subtasks dispatched concurrently to named agents. Use this when the shape of the work isn't known until the goal is.

They aren't three products bolted together — they share one substrate. Every agent reachable from `/agents/route` (`echo`, `summary`, `support_pipeline`, and anything you register) is also invocable as a workflow step. `support_pipeline` wraps the exact same FSM runtime that backs `/messages`, so a workflow step or a routed subtask can run a full customer-support turn as one node in a larger graph:

```json
{
  "name": "Ticket then escalation check",
  "steps": [
    {
      "id": "handle_ticket",
      "kind": "agent",
      "agent_name": "support_pipeline",
      "static_input": {"message": "I want a refund", "customer_id": "cust_1"}
    },
    {
      "id": "check_policy",
      "kind": "tool",
      "tool_name": "refund_policy",
      "depends_on": ["handle_ticket"]
    }
  ]
}
```

See [Getting Started](getting-started.md) to run it, [Architecture](architecture.md) for the component map and request lifecycles, and [Design Decisions](design-decisions.md) for the reasoning behind the three-entry-point shape.
