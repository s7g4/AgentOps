from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, TypeVar

# Re-export from the canonical exceptions module so callers can import
# from either location without breaking changes.
from app.exceptions import ToolExecutionError, ToolInputError, ToolNotFoundError

__all__ = [
    "BaseTool",
    "ToolExecutionError",
    "ToolInputError",
    "ToolNotFoundError",
    # Legacy alias kept for backward compatibility.
    "ToolValidationError",
]

# Backward-compat alias (tests and existing code may import this name).
ToolValidationError = ToolInputError

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


class BaseTool[InputT, OutputT](ABC):
    """Abstract base for all AgentOps tools.

    Each tool owns its own input validation and execution logic.
    The ToolRegistry calls validate_input → execute and enforces that
    outputs are dicts (required for trace serialisation).
    """

    name: str
    description: str

    @abstractmethod
    def validate_input(self, raw: dict[str, Any]) -> InputT:
        """Parse and validate raw input dict.  Raise ToolInputError on failure."""
        raise NotImplementedError

    @abstractmethod
    def execute(self, parsed: InputT) -> OutputT:
        """Run the tool.  Raise ToolExecutionError on failure."""
        raise NotImplementedError
