from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FakeTicket:
    customer_id: str
    message: str


def build_fake_tickets(count: int = 100) -> list[FakeTicket]:
    templates = [
        ("cust-001", "Hi, I need a refund for my order because the item arrived damaged."),
        ("cust-002", "Where is my order #12345? I need the current tracking status."),
        ("cust-003", "This is spam: buy cheap pills now"),
        ("cust-004", "Please escalate this issue to a human because the booking is incorrect."),
        ("cust-005", "Can you tell me the return policy for a late shipment?"),
        ("cust-006", "I have a question about your pricing for the enterprise plan."),
    ]

    tickets: list[FakeTicket] = []
    for index in range(count):
        customer_id, message = templates[index % len(templates)]
        tickets.append(FakeTicket(customer_id=f"{customer_id}-{index}", message=message))

    return tickets
