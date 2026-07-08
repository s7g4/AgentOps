"""Load test for AgentOps' three entry points.

Run against a local instance (memory backends are fine for a smoke run,
but point at Redis-backed backends to get numbers that mean something for
a production-shaped deployment):

    python -m app.main &
    locust -f locustfile.py --host http://localhost:8000

Headless, fixed run:

    locust -f locustfile.py --host http://localhost:8000 \\
        --users 50 --spawn-rate 10 --run-time 2m --headless

Set API_KEY if the target instance has AUTH_ENABLED=true.
"""

from __future__ import annotations

import os
import random
import uuid

from locust import HttpUser, between, task

_API_KEY = os.environ.get("API_KEY")

_MESSAGES = [
    "I want a refund for my last order",
    "Where is my order? It hasn't arrived yet",
    "This product arrived broken, I need a replacement",
    "Can you tell me about your return policy?",
    "I was charged twice for the same order",
]

_SOURCES = ["email", "contact_form", "ticket", "chat"]


class AgentOpsUser(HttpUser):
    wait_time = between(0.5, 2.0)

    def on_start(self) -> None:
        if _API_KEY:
            self.client.headers.update({"X-Api-Key": _API_KEY})

    @task(6)
    def send_message(self) -> None:
        self.client.post(
            "/messages",
            json={
                "source": random.choice(_SOURCES),
                "customer_id": f"cust_{random.randint(1, 10_000)}",
                "message": random.choice(_MESSAGES),
            },
            name="/messages",
        )

    @task(3)
    def route_goal(self) -> None:
        self.client.post(
            "/agents/route",
            json={
                "goal": "summarize and echo this ticket",
                "subtasks": [
                    {"agent_name": "summary", "payload": {"ticket": random.choice(_MESSAGES)}},
                    {"agent_name": "echo", "payload": {"ticket": random.choice(_MESSAGES)}},
                ],
            },
            name="/agents/route",
        )

    @task(1)
    def workflow_roundtrip(self) -> None:
        name = f"loadtest-{uuid.uuid4().hex[:8]}"
        resp = self.client.post(
            "/workflows",
            json={
                "name": name,
                "description": "Load-test workflow: pipeline step then policy check.",
                "steps": [
                    {
                        "id": "handle_ticket",
                        "kind": "agent",
                        "agent_name": "support_pipeline",
                        "static_input": {
                            "message": random.choice(_MESSAGES),
                            "customer_id": f"cust_{random.randint(1, 10_000)}",
                        },
                    },
                    {
                        "id": "check_policy",
                        "kind": "tool",
                        "tool_name": "refund_policy",
                        "depends_on": ["handle_ticket"],
                    },
                ],
            },
            name="/workflows [create]",
        )
        if resp.status_code != 201:
            return

        workflow_id = resp.json()["id"]
        self.client.post(
            f"/workflows/{workflow_id}/run",
            json={},
            name="/workflows/[id]/run",
        )
        self.client.delete(f"/workflows/{workflow_id}", name="/workflows/[id] [delete]")

    @task(2)
    def health(self) -> None:
        self.client.get("/health", name="/health")
