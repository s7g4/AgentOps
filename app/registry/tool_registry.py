from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

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

    def execute(self, name: str, raw_input: dict[str, Any]) -> dict[str, Any]:
        tool = self.get(name)
        parsed = tool.validate_input(raw_input)
        output = tool.execute(parsed)
        # Tools must return structured dict outputs for now.
        if not isinstance(output, dict):
            raise ToolExecutionError(f"Tool {name} output must be dict")
        return output

    @classmethod
    def default(cls) -> ToolRegistry:
        reg = cls()
        reg.register(CheckOrderStatusTool())
        reg.register(RefundPolicyTool())
        return reg
