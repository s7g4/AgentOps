from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class TraceEvent:
    timestamp: str
    name: str
    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TraceEvent:
        return cls(timestamp=d["timestamp"], name=d["name"], data=d.get("data", {}))


ToolCallStatus = Literal["success", "error"]


@dataclass
class ToolCall:
    tool_name: str
    input: dict[str, Any]
    output: dict[str, Any] | None = None
    error: str | None = None
    status: ToolCallStatus = "success"

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ToolCall:
        return cls(
            tool_name=d["tool_name"],
            input=d["input"],
            output=d.get("output"),
            error=d.get("error"),
            status=d.get("status", "success"),
        )


@dataclass
class AgentDecision:
    agent: str
    summary: str
    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AgentDecision:
        return cls(agent=d["agent"], summary=d["summary"], data=d.get("data", {}))


@dataclass
class Trace:
    trace_id: str
    timeline: list[TraceEvent] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    agent_decisions: list[AgentDecision] = field(default_factory=list)
    final_response: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "timeline": [e.__dict__ for e in self.timeline],
            "tool_calls": [
                {
                    "tool_name": tc.tool_name,
                    "input": tc.input,
                    "output": tc.output,
                    "error": tc.error,
                    "status": tc.status,
                }
                for tc in self.tool_calls
            ],
            "agent_decisions": [
                {"agent": ad.agent, "summary": ad.summary, "data": ad.data}
                for ad in self.agent_decisions
            ],
            "final_response": self.final_response,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Trace:
        """Reconstruct a Trace from its dict representation (e.g., from Redis)."""
        return cls(
            trace_id=d["trace_id"],
            timeline=[TraceEvent.from_dict(e) for e in d.get("timeline", [])],
            tool_calls=[ToolCall.from_dict(tc) for tc in d.get("tool_calls", [])],
            agent_decisions=[
                AgentDecision.from_dict(ad) for ad in d.get("agent_decisions", [])
            ],
            final_response=d.get("final_response", {}),
        )
