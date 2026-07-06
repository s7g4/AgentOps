# Contributing to AgentOps

## Setup

```bash
git clone https://github.com/s7g4/AgentOps.git
cd AgentOps
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pip install -e "./client[dev]"
```

## Before opening a PR

```bash
ruff check .                                     # lint
mypy app                                          # type check (strict)
pytest -q --cov=app --cov-report=term-missing     # server test suite
pytest client/tests -q                             # client test suite
```

Redis-backed tests (trace/workflow/routing stores, the Redis rate limiter) skip automatically if no Redis is reachable. To run them locally:

```bash
docker run -d --rm -p 6379:6379 redis:7-alpine
REDIS_URL=redis://localhost:6379/0 pytest -q
```

CI runs the full suite against a real `redis:7-alpine` service container, enforces `ruff check .`, `mypy app` (strict), and a coverage floor via `--cov-fail-under`. A PR that doesn't pass all three won't merge.

## Code style

This isn't enforced by a linter beyond `ruff`, but the codebase is consistent about a few things — match them rather than introducing a new pattern:

- **Provider abstraction**: agent-facing behavior (classification, planning, verification, response generation, decomposition) is an ABC in `app/providers/base.py` or `app/messaging/decomposition.py`, with a deterministic implementation and (optionally) an OpenAI-backed one. New LLM-backed capability follows the same shape — extend, don't special-case.
- **Dataclasses for internal domain objects, Pydantic only at the API boundary.** `WorkflowStep`, `Trace`, `AgentMessage` etc. are dataclasses with `to_dict()`/`from_dict()`. `app/schemas/*.py` is the only place Pydantic models exist, because that's the only place validating untrusted input pays for itself.
- **Two-tier persistence.** Anything that needs to survive a restart or be shared across replicas gets an in-memory implementation (default, zero deps) and a Redis implementation, behind the same `Protocol`. See `app/workflows/store.py` for the shape to copy.
- **Typed exceptions.** New failure modes get a subclass of `AgentOpsError` in `app/exceptions.py`, not a bare `Exception` or a string-matched error path.
- **Docstrings explain *why*, not *what*.** Look at any existing module docstring in `app/` for the expected shape: a design rationale, the alternatives considered, and why this one won.

## Tests

New behavior needs a test in the same style as the surrounding file — plain functions (not test classes) for most things, `async def test_...()` where `pytest-asyncio`'s auto mode picks it up directly. Look at the file you're editing before adding a new pattern.

## Reporting bugs / requesting features

Use the issue templates. The bug template asks for a minimal repro because "it doesn't work" against a system with three orchestration entry points, two persistence backends, and optional LLM providers isn't actionable without knowing which combination you hit.
