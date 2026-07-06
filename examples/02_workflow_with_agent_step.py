"""Build and run a workflow that mixes a tool step and an agent step.

Demonstrates the seam that ties the three orchestration entry points
together: the "handle_ticket" step invokes support_pipeline — the same
FSM pipeline backing POST /messages — as one node in a larger DAG, and
"check_policy" consumes its output via $step.<id>.<key> templating.

Run:
    python -m app.main &
    python examples/02_workflow_with_agent_step.py
"""

from __future__ import annotations

from agentops_client import AgentOpsClient


def main() -> None:
    with AgentOpsClient(base_url="http://localhost:8000") as client:
        workflow = client.create_workflow(
            name="ticket-then-policy-check",
            description="Run a ticket through the FSM pipeline, then check refund policy.",
            steps=[
                {
                    "id": "handle_ticket",
                    "kind": "agent",
                    "agent_name": "support_pipeline",
                    "static_input": {
                        "message": "I want a refund",
                        "customer_id": "cust_456",
                    },
                },
                {
                    "id": "check_policy",
                    "kind": "tool",
                    "tool_name": "refund_policy",
                    "depends_on": ["handle_ticket"],
                },
            ],
        )
        print(f"created workflow {workflow.id}")

        execution = client.run_workflow(workflow.id)
        print(f"status: {execution.status}")
        for step_id, result in execution.step_results.items():
            print(f"  {step_id}: {result.status} -> {result.output}")


if __name__ == "__main__":
    main()
