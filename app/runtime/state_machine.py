from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RuntimeState(StrEnum):
    RECEIVED = "RECEIVED"
    CLASSIFIED = "CLASSIFIED"
    PLANNING = "PLANNING"
    TOOL_EXECUTION = "TOOL_EXECUTION"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


# Legal forward transitions. FAILED is reachable from any state.
VALID_TRANSITIONS: dict[RuntimeState, frozenset[RuntimeState]] = {
    RuntimeState.RECEIVED: frozenset({RuntimeState.CLASSIFIED, RuntimeState.FAILED}),
    RuntimeState.CLASSIFIED: frozenset({RuntimeState.PLANNING, RuntimeState.FAILED}),
    RuntimeState.PLANNING: frozenset({RuntimeState.TOOL_EXECUTION, RuntimeState.FAILED}),
    RuntimeState.TOOL_EXECUTION: frozenset({RuntimeState.VERIFYING, RuntimeState.FAILED}),
    RuntimeState.VERIFYING: frozenset({RuntimeState.COMPLETED, RuntimeState.FAILED}),
    RuntimeState.COMPLETED: frozenset(),
    RuntimeState.FAILED: frozenset(),
}


class InvalidTransitionError(Exception):
    """Raised when the runtime attempts an illegal state transition."""


@dataclass
class Transition:
    from_state: RuntimeState
    to_state: RuntimeState
    reason: str


def validate_transition(from_state: RuntimeState, to_state: RuntimeState) -> None:
    """Raise InvalidTransitionError if the transition is not permitted."""
    allowed = VALID_TRANSITIONS.get(from_state, frozenset())
    if to_state not in allowed:
        raise InvalidTransitionError(
            f"Illegal transition {from_state} → {to_state}. "
            f"Allowed: {sorted(s.value for s in allowed) or 'none'}"
        )
