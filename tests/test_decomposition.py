"""Tests for DeterministicDecompositionProvider."""

from __future__ import annotations

import asyncio

from app.messaging.decomposition import DeterministicDecompositionProvider


def test_deterministic_decomposer_keyword_mapping() -> None:
    provider = DeterministicDecompositionProvider()
    agents = ["echo", "summary"]

    # Goal containing "echo"
    subtasks = asyncio.run(provider.decompose("Please echo this message", agents))
    assert len(subtasks) == 1
    assert subtasks[0].agent_name == "echo"
    assert subtasks[0].payload["message"] == "Please echo this message"

    # Goal containing "summar"
    subtasks = asyncio.run(provider.decompose("summarize this support request", agents))
    assert len(subtasks) == 1
    assert subtasks[0].agent_name == "summary"

    # Goal containing both
    subtasks = asyncio.run(provider.decompose("echo and summarize this", agents))
    assert len(subtasks) == 2
    assert {s.agent_name for s in subtasks} == {"echo", "summary"}

    # Goal containing neither (fallback to echo)
    subtasks = asyncio.run(provider.decompose("random intent", agents))
    assert len(subtasks) == 1
    assert subtasks[0].agent_name == "echo"
