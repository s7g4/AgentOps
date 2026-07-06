# agentops-client

Python client and CLI for the [AgentOps](../README.md) API.

## Install

```bash
pip install -e ./client
```

## CLI

```bash
export AGENTOPS_BASE_URL=http://localhost:8000   # default
export AGENTOPS_API_KEY=...                       # only if AUTH_ENABLED=true

agentops health
agentops tools
agentops send "I want a refund" --customer-id cust_1

agentops workflows create --file workflow.json
agentops workflows run <workflow-id>
agentops workflows run <workflow-id> --background
agentops workflows runs <workflow-id> --execution-id <execution-id>

agentops agents list
agentops agents route "please summarize this ticket"
```

Every command prints JSON to stdout, so it composes with `jq`:

```bash
agentops workflows run <workflow-id> | jq '.step_results'
```

## Library

```python
from agentops_client import AgentOpsClient

with AgentOpsClient(base_url="http://localhost:8000") as client:
    result = client.send_message(message="I want a refund", customer_id="cust_1")
    print(result.intent, result.response)
```

For an async application, use `AsyncAgentOpsClient` directly instead — the sync
`AgentOpsClient` opens a fresh connection per call (via its own `asyncio.run()`),
which is the right tradeoff for a CLI or script but not for a long-running
async service that wants connection reuse.

```python
from agentops_client import AsyncAgentOpsClient

async with AsyncAgentOpsClient(base_url="http://localhost:8000") as client:
    workflow = await client.create_workflow(
        name="ticket-then-policy-check",
        steps=[
            {
                "id": "handle",
                "kind": "agent",
                "agent_name": "support_pipeline",
                "static_input": {"message": "I want a refund", "customer_id": "cust_1"},
            },
            {"id": "policy", "kind": "tool", "tool_name": "refund_policy", "depends_on": ["handle"]},
        ],
    )
    execution = await client.run_workflow(workflow.id)
```

## Testing

```bash
pip install -e "./client[dev]"
pytest client/tests -q
```

Tests run against the real AgentOps ASGI app via `httpx.ASGITransport` (no live server, no network) for the client library, and against a real subprocess for the CLI end-to-end tests.
