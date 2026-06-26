"""Tests for ToolRegistry: registration, execution, error handling."""
from __future__ import annotations

from typing import Any

import pytest

from app.registry.tool_registry import ToolRegistry
from app.tools.base import BaseTool, ToolExecutionError, ToolValidationError


class EchoTool(BaseTool[dict[str, Any], dict[str, Any]]):
    name = "echo"
    description = "Returns what it receives."

    def validate_input(self, raw: dict[str, Any]) -> dict[str, Any]:
        return raw

    def execute(self, parsed: dict[str, Any]) -> dict[str, Any]:
        return parsed


class FailingTool(BaseTool[dict[str, Any], dict[str, Any]]):
    name = "failing"
    description = "Always raises."

    def validate_input(self, raw: dict[str, Any]) -> dict[str, Any]:
        return raw

    def execute(self, parsed: dict[str, Any]) -> dict[str, Any]:
        raise ToolExecutionError("boom")


class BadOutputTool(BaseTool[dict[str, Any], Any]):
    name = "bad_output"
    description = "Returns a non-dict."

    def validate_input(self, raw: dict[str, Any]) -> dict[str, Any]:
        return raw

    def execute(self, parsed: dict[str, Any]) -> Any:  # noqa: ANN401
        return "not a dict"


class TestToolRegistryRegistration:
    def test_register_and_list(self) -> None:
        reg = ToolRegistry()
        reg.register(EchoTool())
        assert "echo" in reg.names()

    def test_duplicate_registration_raises(self) -> None:
        reg = ToolRegistry()
        reg.register(EchoTool())
        with pytest.raises(ValueError, match="already registered"):
            reg.register(EchoTool())

    def test_get_registered_tool(self) -> None:
        reg = ToolRegistry()
        tool = EchoTool()
        reg.register(tool)
        assert reg.get("echo") is tool

    def test_get_missing_tool_raises(self) -> None:
        reg = ToolRegistry()
        with pytest.raises(KeyError):
            reg.get("nonexistent")


class TestToolRegistryExecution:
    def test_execute_echo_tool(self) -> None:
        reg = ToolRegistry()
        reg.register(EchoTool())
        result = reg.execute("echo", {"key": "val"})
        assert result == {"key": "val"}

    def test_execute_missing_tool_raises(self) -> None:
        reg = ToolRegistry()
        with pytest.raises(KeyError):
            reg.execute("nonexistent", {})

    def test_execute_raises_on_tool_error(self) -> None:
        reg = ToolRegistry()
        reg.register(FailingTool())
        with pytest.raises(ToolExecutionError, match="boom"):
            reg.execute("failing", {})

    def test_execute_raises_on_non_dict_output(self) -> None:
        reg = ToolRegistry()
        reg.register(BadOutputTool())
        with pytest.raises(ToolExecutionError, match="must be dict"):
            reg.execute("bad_output", {})

    def test_default_registry_has_expected_tools(self) -> None:
        reg = ToolRegistry.default()
        names = reg.names()
        assert "check_order_status" in names
        assert "refund_policy" in names

    def test_refund_policy_output(self) -> None:
        reg = ToolRegistry.default()
        out = reg.execute("refund_policy", {})
        assert "policy" in out
        assert "30 days" in out["policy"]

    def test_check_order_status_success(self) -> None:
        reg = ToolRegistry.default()
        out = reg.execute("check_order_status", {"order_id": "valid-123"})
        assert out["status"] == "shipped"
        assert out["eta_days"] == 3

    def test_check_order_status_missing_order_raises(self) -> None:
        reg = ToolRegistry.default()
        with pytest.raises(ToolExecutionError, match="order not found"):
            reg.execute("check_order_status", {"order_id": "missing-xyz"})

    def test_check_order_status_invalid_input_raises(self) -> None:
        reg = ToolRegistry.default()
        with pytest.raises(ToolValidationError, match="order_id is required"):
            reg.execute("check_order_status", {})
