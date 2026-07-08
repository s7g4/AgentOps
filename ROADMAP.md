# Roadmap

## Final goal

A self-hostable multi-agent orchestration backend with a public demo, a published PyPI SDK, a docs site, and a security/load-test pass — so nobody can ask "is this real." This is already the strongest project in the portfolio; the goal is polish to a "can't top that" v1, not a rewrite.

## Current state (~90%)

- 60 commits over 11 days, 9.3K LoC, 30 real tests, 80% coverage enforced in CI.
- README claims match the code exactly — FSM pipeline, DAG workflow engine, and agent router genuinely share one substrate.
- Redis-backed persistence and rate-limiting both have in-memory and Redis implementations behind shared interfaces; CI runs against a real Redis service container, not a mock.
- OpenAI-backed decomposition is real and optional (falls back to a deterministic keyword matcher without a key).

## Phased plan to final goal

1. **Publish-readiness** — verify `pip install -e ".[dev]"` and `python -m app.main` work from a clean clone. Correct `pyproject.toml` metadata (description, classifiers, license, urls) for real PyPI publication.
2. **Docs site** — stand up mkdocs-material (or expand README into a docs/ dir) covering architecture, API reference, and the three entry points.
3. **Security/load-test pass** — review auth/rate-limit/CORS defaults; add a k6 or locust script exercising `/messages`.
4. **Deployment** — confirm Docker Compose builds clean; prepare Fly.io/Render config so it's one-command deployable.
5. **Design-decision writeup** — a short technical post on the three-entry-point/one-substrate architecture. Highest-signal artifact for a job search.

## Owner-gated steps (need your accounts/credentials)

- PyPI account + token to actually run `python -m build && twine upload`.
- Cloud hosting signup (Fly.io/Render) to deploy the live demo.
- A custom domain if you want a branded demo URL.
