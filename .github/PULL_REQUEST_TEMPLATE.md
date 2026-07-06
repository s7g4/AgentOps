## What this changes and why

## Checklist

- [ ] `ruff check .` passes
- [ ] `mypy app` passes (strict)
- [ ] `pytest -q --cov=app --cov-report=term-missing` passes, coverage didn't drop
- [ ] `pytest client/tests -q` passes (if `client/` touched)
- [ ] New behavior has a test in the style of the surrounding file
- [ ] Docs updated (`README.md` / `docs/architecture.md`) if this changes an API, config variable, or the orchestration model

## Test plan

How did you verify this manually, beyond the automated tests?
