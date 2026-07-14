from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from tenacity import retry, stop_after_attempt, wait_fixed

from app.runtime.metrics import TOOL_EXECUTION_LATENCY_SECONDS, TOOL_EXECUTION_TOTAL
from app.tools.base import BaseTool, ToolExecutionError
from app.tools.example_tools import CheckOrderStatusTool, RefundPolicyTool


@dataclass
class ToolRegistry:
    _tools: dict[str, BaseTool[Any, Any]] = field(default_factory=dict)

    def register(self, tool: BaseTool[Any, Any]) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def get(self, name: str) -> BaseTool[Any, Any]:
        if name not in self._tools:
            raise KeyError(name)
        return self._tools[name]

    @retry(stop=stop_after_attempt(2), wait=wait_fixed(0.2), reraise=True)
    def execute(self, name: str, raw_input: dict[str, Any]) -> dict[str, Any]:
        """Validate input, run the tool, and record metrics — the single
        dispatch path every caller (FSM pipeline, workflow steps) goes
        through, so retry/metrics behavior is identical regardless of which
        entry point invoked the tool."""
        start = time.perf_counter()
        status = "success"
        try:
            tool = self.get(name)
            parsed = tool.validate_input(raw_input)
            output = tool.execute(parsed)
            # Tools must return structured dict outputs for now.
            if not isinstance(output, dict):
                raise ToolExecutionError(f"Tool {name} output must be dict")
            return output
        except Exception:
            status = "error"
            raise
        finally:
            TOOL_EXECUTION_TOTAL.labels(tool_name=name, status=status).inc()
            TOOL_EXECUTION_LATENCY_SECONDS.labels(tool_name=name).observe(
                time.perf_counter() - start
            )

    @classmethod
    def default(cls) -> ToolRegistry:
        reg = cls()
        reg.register(CheckOrderStatusTool())
        reg.register(RefundPolicyTool())
        return reg
