"""Tests for WorkflowDefinition validation and execution_layers()."""

from __future__ import annotations

import pytest

from app.workflows.definition import WorkflowDefinition, WorkflowStep


def _make_step(sid: str, depends_on: list[str] | None = None) -> WorkflowStep:
    return WorkflowStep(id=sid, tool_name="refund_policy", depends_on=depends_on or [])


# ── validate(): duplicate IDs ─────────────────────────────────────────────────

def test_validate_rejects_duplicate_step_ids() -> None:
    wf = WorkflowDefinition(
        name="dup",
        steps=[_make_step("a"), _make_step("a")],
    )
    with pytest.raises(ValueError, match="Duplicate step ID"):
        wf.validate()


# ── validate(): dangling deps ─────────────────────────────────────────────────

def test_validate_rejects_dangling_dependency() -> None:
    wf = WorkflowDefinition(
        name="dangling",
        steps=[_make_step("a", depends_on=["nonexistent"])],
    )
    with pytest.raises(ValueError, match="unknown step"):
        wf.validate()


# ── validate(): cycles ────────────────────────────────────────────────────────

def test_validate_rejects_direct_cycle() -> None:
    """a → b → a"""
    wf = WorkflowDefinition(
        name="cycle",
        steps=[
            _make_step("a", depends_on=["b"]),
            _make_step("b", depends_on=["a"]),
        ],
    )
    with pytest.raises(ValueError, match="cycle"):
        wf.validate()


def test_validate_rejects_three_node_cycle() -> None:
    """a → b → c → a"""
    wf = WorkflowDefinition(
        name="tri-cycle",
        steps=[
            _make_step("a", depends_on=["c"]),
            _make_step("b", depends_on=["a"]),
            _make_step("c", depends_on=["b"]),
        ],
    )
    with pytest.raises(ValueError, match="cycle"):
        wf.validate()


def test_validate_passes_on_valid_dag() -> None:
    wf = WorkflowDefinition(
        name="valid",
        steps=[
            _make_step("a"),
            _make_step("b", depends_on=["a"]),
            _make_step("c", depends_on=["a"]),
            _make_step("d", depends_on=["b", "c"]),
        ],
    )
    wf.validate()  # must not raise


# ── execution_layers() ────────────────────────────────────────────────────────

def test_single_step_is_one_layer() -> None:
    wf = WorkflowDefinition(name="single", steps=[_make_step("a")])
    layers = wf.execution_layers()
    assert len(layers) == 1
    assert layers[0][0].id == "a"


def test_independent_steps_form_one_layer() -> None:
    wf = WorkflowDefinition(
        name="parallel",
        steps=[_make_step("a"), _make_step("b"), _make_step("c")],
    )
    layers = wf.execution_layers()
    assert len(layers) == 1
    assert {s.id for s in layers[0]} == {"a", "b", "c"}


def test_chain_produces_sequential_layers() -> None:
    """a → b → c should produce 3 layers."""
    wf = WorkflowDefinition(
        name="chain",
        steps=[
            _make_step("a"),
            _make_step("b", depends_on=["a"]),
            _make_step("c", depends_on=["b"]),
        ],
    )
    layers = wf.execution_layers()
    assert len(layers) == 3
    assert layers[0][0].id == "a"
    assert layers[1][0].id == "b"
    assert layers[2][0].id == "c"


def test_diamond_dag_layers() -> None:
    """
        a
       / \\
      b   c
       \\ /
        d
    Layers: [a], [b, c], [d]
    """
    wf = WorkflowDefinition(
        name="diamond",
        steps=[
            _make_step("a"),
            _make_step("b", depends_on=["a"]),
            _make_step("c", depends_on=["a"]),
            _make_step("d", depends_on=["b", "c"]),
        ],
    )
    layers = wf.execution_layers()
    assert len(layers) == 3
    assert layers[0][0].id == "a"
    assert {s.id for s in layers[1]} == {"b", "c"}
    assert layers[2][0].id == "d"


# ── serialisation ─────────────────────────────────────────────────────────────

def test_roundtrip_serialisation() -> None:
    wf = WorkflowDefinition(
        name="rt",
        description="roundtrip",
        steps=[
            _make_step("a"),
            _make_step("b", depends_on=["a"]),
        ],
    )
    restored = WorkflowDefinition.from_dict(wf.to_dict())
    assert restored.id == wf.id
    assert restored.name == wf.name
    assert len(restored.steps) == 2
    assert restored.steps[1].depends_on == ["a"]
