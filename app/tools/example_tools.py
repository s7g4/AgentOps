from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.tools.base import BaseTool, ToolExecutionError, ToolValidationError


@dataclass
class OrderStatusInput:
    order_id: str


@dataclass
class OrderStatusOutput:
    order_id: str
    status: str
    eta_days: int | None = None


class CheckOrderStatusTool(BaseTool[dict[str, Any], dict[str, Any]]):
    name = "check_order_status"
    description = "Check order status given an order_id."

    def validate_input(self, raw: dict[str, Any]) -> dict[str, Any]:
        if (
            "order_id" not in raw
            or not isinstance(raw["order_id"], str)
            or not raw["order_id"].strip()
        ):
            raise ToolValidationError("order_id is required")
        return raw

    def execute(self, parsed: dict[str, Any]) -> dict[str, Any]:
        order_id = parsed["order_id"].strip()
        # Stub implementation: in Phase-2 we'll integrate DB/CRM.
        if order_id.lower().startswith("missing"):
            raise ToolExecutionError("order not found")
        return {"order_id": order_id, "status": "shipped", "eta_days": 3}


@dataclass
class RefundPolicyOutput:
    policy: str


class RefundPolicyTool(BaseTool[dict[str, Any], dict[str, Any]]):
    name = "refund_policy"
    description = "Return the refund policy for the merchant."

    def validate_input(self, raw: dict[str, Any]) -> dict[str, Any]:
        return raw

    def execute(self, parsed: dict[str, Any]) -> dict[str, Any]:
        return {
            "policy": (
                "Refunds accepted within 30 days of delivery. "
                "Original payment method used for refunds."
            )
        }
