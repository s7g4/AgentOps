from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ToolPlan:
    tool_calls: list[dict[str, Any]]
