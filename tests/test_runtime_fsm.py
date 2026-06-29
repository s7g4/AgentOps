"""Tests for the FSM state machine transition table enforcement."""
from __future__ import annotations

import pytest

from app.runtime.state_machine import (
    InvalidTransitionError,
    RuntimeState,
    validate_transition,
)


def test_valid_linear_transitions() -> None:
    """Each stage in the happy path is a valid transition."""
    path = [
        (RuntimeState.RECEIVED, RuntimeState.CLASSIFIED),
        (RuntimeState.CLASSIFIED, RuntimeState.PLANNING),
        (RuntimeState.PLANNING, RuntimeState.TOOL_EXECUTION),
        (RuntimeState.TOOL_EXECUTION, RuntimeState.VERIFYING),
        (RuntimeState.VERIFYING, RuntimeState.COMPLETED),
    ]
    for from_s, to_s in path:
        validate_transition(from_s, to_s)  # Must not raise.


def test_all_states_can_transition_to_failed() -> None:
    """Every non-terminal state must allow a FAILED transition."""
    non_terminal = [
        RuntimeState.RECEIVED,
        RuntimeState.CLASSIFIED,
        RuntimeState.PLANNING,
        RuntimeState.TOOL_EXECUTION,
        RuntimeState.VERIFYING,
    ]
    for state in non_terminal:
        validate_transition(state, RuntimeState.FAILED)  # Must not raise.


def test_completed_state_has_no_outgoing_transitions() -> None:
    for target in RuntimeState:
        if target != RuntimeState.COMPLETED:
            with pytest.raises(InvalidTransitionError):
                validate_transition(RuntimeState.COMPLETED, target)


def test_failed_state_has_no_outgoing_transitions() -> None:
    for target in RuntimeState:
        if target != RuntimeState.FAILED:
            with pytest.raises(InvalidTransitionError):
                validate_transition(RuntimeState.FAILED, target)


def test_illegal_skip_transition_raises() -> None:
    """Skipping CLASSIFIED → directly to PLANNING is illegal."""
    with pytest.raises(InvalidTransitionError):
        validate_transition(RuntimeState.RECEIVED, RuntimeState.PLANNING)


def test_backwards_transition_raises() -> None:
    """Going COMPLETED → RECEIVED is illegal."""
    with pytest.raises(InvalidTransitionError):
        validate_transition(RuntimeState.COMPLETED, RuntimeState.RECEIVED)


def test_invalid_transition_error_message() -> None:
    """Error message should name both states."""
    with pytest.raises(InvalidTransitionError, match="RECEIVED"):
        validate_transition(RuntimeState.RECEIVED, RuntimeState.VERIFYING)
