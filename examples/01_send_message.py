"""Send a single message through the classify/plan/execute/verify/respond pipeline.

Run:
    python -m app.main &
    python examples/01_send_message.py
"""

from __future__ import annotations

from agentops_client import AgentOpsClient


def main() -> None:
    with AgentOpsClient(base_url="http://localhost:8000") as client:
        result = client.send_message(
            message="I want a refund for my last order",
            customer_id="cust_123",
            source="ticket",
        )
        print(f"intent:     {result.intent}")
        print(f"confidence: {result.confidence}")
        print(f"escalated:  {result.escalated}")
        print(f"response:   {result.response}")

        trace = client.get_trace(result.trace_id)
        print(f"\ntrace has {len(trace['timeline'])} timeline events")


if __name__ == "__main__":
    main()
