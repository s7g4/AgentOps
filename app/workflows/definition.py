"""Workflow definition data model.

A WorkflowDefinition is a named, versioned directed acyclic graph (DAG)
of WorkflowSteps.  Each step references a ToolRegistry tool by name and
declares its data dependencies via depends_on.

Validation
──────────
WorkflowDefinition.validate() enforces three invariants at definition time
(not at execution time) so that invalid graphs are rejected before any work:

  1. No duplicate step IDs.
  2. All depends_on references point to a step ID that exists in this
     workflow (no dangling edges).
  3. No cycles — detected via Kahn's algorithm (topological sort).

Design choice: dataclasses not Pydantic
────────────────────────────────────────
Consistent with Trace, TraceEvent, ToolCall — internal domain objects use
dataclasses for zero overhead.  Pydantic is used only at the API boundary
(app/schemas/workflow.py).
"""

from __future__ import annotations

import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from app.schemas.trace import utc_now_iso


@dataclass
class WorkflowStep:
    """A single executable node in a workflow DAG.

    Attributes
    ----------
    id:           Unique identifier within this workflow.
    tool_name:    Name of a registered tool to execute.
    static_input: Input dict merged with runtime context before execution.
    depends_on:   IDs of steps that must succeed before this step runs.
    """

    id: str
    tool_name: str
    static_input: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tool_name": self.tool_name,
            "static_input": self.static_input,
            "depends_on": self.depends_on,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> WorkflowStep:
        return cls(
            id=d["id"],
            tool_name=d["tool_name"],
            static_input=d.get("static_input", {}),
            depends_on=d.get("depends_on", []),
        )


@dataclass
class WorkflowDefinition:
    """A named, versioned DAG of workflow steps.

    Attributes
    ----------
    id:          Globally unique workflow identifier (UUID).
    name:        Human-readable name.
    description: Optional description.
    steps:       Ordered list of WorkflowStep nodes.
    created_at:  ISO-8601 UTC timestamp.
    updated_at:  ISO-8601 UTC timestamp (updated on PUT).
    """

    name: str
    steps: list[WorkflowStep]
    description: str = ""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    # ── Validation ────────────────────────────────────────────────────────────

    def validate(self) -> None:
        """Validate DAG invariants.  Raises ValueError on first violation."""
        self._check_duplicate_ids()
        self._check_dangling_deps()
        self._check_cycles()

    def _check_duplicate_ids(self) -> None:
        seen: set[str] = set()
        for step in self.steps:
            if step.id in seen:
                raise ValueError(f"Duplicate step ID: {step.id!r}")
            seen.add(step.id)

    def _check_dangling_deps(self) -> None:
        ids = {s.id for s in self.steps}
        for step in self.steps:
            for dep in step.depends_on:
                if dep not in ids:
                    raise ValueError(
                        f"Step {step.id!r} depends on unknown step {dep!r}"
                    )

    def _check_cycles(self) -> None:
        """Kahn's algorithm — if topological sort cannot consume all nodes, a cycle exists."""
        in_degree: dict[str, int] = {s.id: 0 for s in self.steps}
        adjacency: dict[str, list[str]] = {s.id: [] for s in self.steps}

        for step in self.steps:
            for dep in step.depends_on:
                adjacency[dep].append(step.id)
                in_degree[step.id] += 1

        queue: deque[str] = deque(sid for sid, deg in in_degree.items() if deg == 0)
        visited = 0
        while queue:
            node = queue.popleft()
            visited += 1
            for neighbour in adjacency[node]:
                in_degree[neighbour] -= 1
                if in_degree[neighbour] == 0:
                    queue.append(neighbour)

        if visited != len(self.steps):
            raise ValueError(
                "Workflow contains a cycle — topological sort could not complete."
            )

    # ── Execution helpers ─────────────────────────────────────────────────────

    def execution_layers(self) -> list[list[WorkflowStep]]:
        """Return steps grouped into parallel execution layers.

        Layer 0 contains steps with no dependencies.
        Layer N contains steps whose all dependencies are in layers 0..N-1.

        The result is a list of lists — each inner list can be executed
        concurrently via asyncio.gather.
        """
        completed: set[str] = set()
        remaining = list(self.steps)
        layers: list[list[WorkflowStep]] = []

        while remaining:
            # Collect all steps whose deps are all in `completed`.
            ready = [s for s in remaining if all(d in completed for d in s.depends_on)]
            if not ready:
                # Should never happen after validate() — defensive guard.
                raise ValueError(
                    "Cannot compute execution layers: circular or unresolvable dependencies."
                )
            layers.append(ready)
            for s in ready:
                completed.add(s.id)
                remaining.remove(s)

        return layers

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "steps": [s.to_dict() for s in self.steps],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> WorkflowDefinition:
        return cls(
            id=d["id"],
            name=d["name"],
            description=d.get("description", ""),
            steps=[WorkflowStep.from_dict(s) for s in d.get("steps", [])],
            created_at=d["created_at"],
            updated_at=d["updated_at"],
        )
