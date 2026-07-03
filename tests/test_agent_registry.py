"""Tests for AgentRegistry — register, get, duplicate, not-found."""

from __future__ import annotations

import pytest

from app.agents.builtin import EchoAgent, SummaryAgent
from app.agents.registry import AgentRegistry
from app.exceptions import AgentNotFoundError
from app.messaging.message import AgentMessage


# ── Register ──────────────────────────────────────────────────────────────────

def test_register_and_get() -> None:
    reg = AgentRegistry()
    reg.register(EchoAgent())
    agent = reg.get("echo")
    assert agent.name == "echo"


def test_register_duplicate_raises() -> None:
    reg = AgentRegistry()
    reg.register(EchoAgent())
    with pytest.raises(ValueError, match="already registered"):
        reg.register(EchoAgent())


def test_get_missing_raises_agent_not_found() -> None:
    reg = AgentRegistry()
    with pytest.raises(AgentNotFoundError):
        reg.get("does_not_exist")


# ── Names / descriptions ──────────────────────────────────────────────────────

def test_names_returns_sorted_list() -> None:
    reg = AgentRegistry()
    reg.register(SummaryAgent())
    reg.register(EchoAgent())
    assert reg.names() == ["echo", "summary"]


def test_descriptions_returns_name_and_description() -> None:
    reg = AgentRegistry()
    reg.register(EchoAgent())
    descs = reg.descriptions()
    assert len(descs) == 1
    assert descs[0]["name"] == "echo"
    assert "description" in descs[0]


def test_len_reflects_registered_count() -> None:
    reg = AgentRegistry()
    assert len(reg) == 0
    reg.register(EchoAgent())
    assert len(reg) == 1
    reg.register(SummaryAgent())
    assert len(reg) == 2


# ── Default factory ───────────────────────────────────────────────────────────

def test_default_registry_has_builtin_agents() -> None:
    reg = AgentRegistry.default()
    assert "echo" in reg.names()
    assert "summary" in reg.names()
    assert len(reg) == 2
