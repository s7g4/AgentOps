"""AgentOps typed exception hierarchy.

Design rationale
────────────────
Catching bare ``Exception`` everywhere produces two problems:

1. Every failure maps to HTTP 500, even validation errors (should be 400).
2. Log context is lost — you can't distinguish "tool not found" from
   "OpenAI API quota exceeded" from "Redis unavailable".

A typed hierarchy lets middleware map exception types to HTTP status codes,
lets callers catch exactly the errors they can handle, and lets log lines
carry a ``code`` field that is queryable in any log aggregation system.

Hierarchy
─────────
AgentOpsError
 ├── ConfigurationError        — missing / invalid config at startup
 ├── ClassificationError       — classifier agent failure
 ├── PlanningError             — planner agent failure
 ├── ToolError                 — base for all tool failures
 │    ├── ToolNotFoundError    — name not in registry
 │    ├── ToolInputError       — input validation failed
 │    └── ToolExecutionError   — tool.execute() raised
 ├── VerificationError         — verifier agent fatal error (≠ escalation)
 ├── AuthError                 — authentication / authorisation failure
 ├── RateLimitError            — request rate exceeded
 └── WorkflowError             — workflow engine (Version 3)
"""

from __future__ import annotations


class AgentOpsError(Exception):
    """Base class for all AgentOps domain exceptions.

    Carries an optional machine-readable ``code`` (defaults to the class
    name) so that log aggregation and API error bodies are queryable.
    """

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code: str = code or type(self).__name__

    def __str__(self) -> str:
        return f"[{self.code}] {super().__str__()}"


# ── Configuration ──────────────────────────────────────────────────────────────

class ConfigurationError(AgentOpsError):
    """Raised when required configuration is missing or invalid at startup.

    Callers should treat this as non-recoverable and crash the process.
    """


# ── Agent layer ────────────────────────────────────────────────────────────────

class ClassificationError(AgentOpsError):
    """Raised when the ClassifierAgent cannot produce a Classification."""


class PlanningError(AgentOpsError):
    """Raised when the PlannerAgent cannot produce a valid ToolPlan."""


class VerificationError(AgentOpsError):
    """Raised when the VerifierAgent encounters a fatal error.

    Distinct from *escalation*, which is a normal business outcome.
    """


# ── Tool layer ─────────────────────────────────────────────────────────────────

class ToolError(AgentOpsError):
    """Base class for all tool-related failures."""


class ToolNotFoundError(ToolError):
    """Raised when a tool name is not registered in ToolRegistry."""


class ToolInputError(ToolError):
    """Raised when tool input fails schema validation.

    HTTP mapping: 400 Bad Request.
    """


class ToolExecutionError(ToolError):
    """Raised when a tool's ``execute()`` method raises an error.

    HTTP mapping: 502 Bad Gateway (upstream tool failure).
    """


# ── HTTP / transport layer ─────────────────────────────────────────────────────

class AuthError(AgentOpsError):
    """Raised when a request cannot be authenticated.

    HTTP mapping: 401 Unauthorized.
    """


class RateLimitError(AgentOpsError):
    """Raised when a caller exceeds their request rate allowance.

    HTTP mapping: 429 Too Many Requests.
    """


# ── Workflow engine (Version 3 placeholder) ────────────────────────────────────

class WorkflowError(AgentOpsError):
    """Base class for workflow engine errors (implemented in Version 3)."""


class WorkflowNotFoundError(WorkflowError):
    """Raised when a workflow ID does not exist."""


class WorkflowExecutionError(WorkflowError):
    """Raised when workflow step execution fails."""

# ── Multi-agent messaging (Version 4) ─────────────────────────────────────────

class AgentError(AgentOpsError):
    """Base class for multi-agent messaging errors."""


class AgentNotFoundError(AgentError):
    """Raised when an agent name is not registered in AgentRegistry."""


class AgentRoutingError(AgentError):
    """Raised when the supervisor cannot route a subtask."""
