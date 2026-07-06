---
name: Bug report
about: Something is broken
title: ""
labels: bug
---

## What happened

## What you expected

## Minimal repro

Which entry point (`/messages`, `/workflows`, `/agents/route`), which backend config (`TRACE_BACKEND`, `RATE_LIMIT_BACKEND`, `AUTH_ENABLED`), and whether an LLM provider (`OPENAI_API_KEY`) was configured. A request body / workflow definition that reproduces it is ideal.

```bash
curl -s http://localhost:8000/... -d '{...}'
```

## Environment

- AgentOps version / commit:
- Python version:
- `REDIS_URL` configured? memory or redis backend?
- Relevant environment variables (redact secrets):

## Logs / trace

If you have a `trace_id`, paste the output of `GET /trace/{trace_id}`.
