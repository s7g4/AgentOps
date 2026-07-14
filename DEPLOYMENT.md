# Deployment

AgentOps is a stateless FastAPI process plus Redis. Any platform that runs a container and gives you a Redis instance works. This covers three paths: self-hosting via Docker Compose, and two managed platforms (Fly.io, Render) with ready-to-use config. **If you want to deploy without a card on file, use Option C (Render)** — Fly.io requires payment info even for low-usage apps; Render's free plan doesn't.

## Production checklist

Set these before exposing the service publicly:

| Variable | Production value | Why |
|---|---|---|
| `AUTH_ENABLED` | `true` | Without this, every endpoint is open. |
| `API_KEYS` | one or more long random strings, comma-separated | Callers authenticate with `X-Api-Key`. Generate with `openssl rand -hex 32`. |
| `REDIS_URL` | your Redis connection string | Required for `TRACE_BACKEND=redis` / `RATE_LIMIT_BACKEND=redis`. |
| `TRACE_BACKEND` | `redis` | In-memory traces vanish on restart and don't share across replicas. |
| `RATE_LIMIT_BACKEND` | `redis` | Same reasoning — in-memory only rate-limits per replica. |
| `OPENAI_API_KEY` | your key, if you want LLM-backed classification/planning/decomposition | Optional — deterministic providers work with no key at all. |
| `TRUST_PROXY_HEADERS` | `true`, **only** if you put a reverse proxy (Caddy, nginx, your platform's load balancer) in front | Enables reading the real client IP from `X-Forwarded-For` for rate limiting and logging. Leave `false` if the app is reachable directly — otherwise a caller can reset their own rate-limit bucket by sending a fresh spoofed header on every request. |

Everything else (`HOST`, `PORT`, `LOG_LEVEL`, `OTEL_*`) has a sane default; see the config table in [README.md](https://github.com/s7g4/AgentOps/blob/main/README.md).

`GET /health` is what your platform's health check / readiness probe should hit — it reports Redis and OpenAI connectivity, not just process liveness.

---

## Option A — Docker Compose (any VPS)

The included `docker-compose.yml` builds the app and wires it to a Redis instance with a persistent volume, on an internal network Redis is never exposed to the host from. This has been verified end to end: build, boot, Redis health check, a trace surviving an app-container restart.

```bash
cp .env.example .env   # fill in API_KEYS, OPENAI_API_KEY if you want it
docker compose up -d --build
curl http://localhost:8000/health
```

Put a reverse proxy in front for TLS — [Caddy](https://caddyserver.com/) is the least ceremony:

```
agentops.yourdomain.com {
    reverse_proxy localhost:8000
}
```

Caddy provisions and renews the certificate automatically; no manual ACME setup.

## Option B — Fly.io

Requires payment info on the account even for a low-usage app (Fly no longer has a no-card free tier) — skip to Option C if you'd rather not add one. `fly.toml` is included. Managed Redis: either Fly's own Redis via `fly redis create`, or a free-tier external one (Upstash), either way you get a `redis://...` URL.

```bash
flyctl launch --no-deploy         # picks up fly.toml, creates the app
flyctl redis create               # or point REDIS_URL at Upstash/another managed Redis
flyctl secrets set \
  API_KEYS="$(openssl rand -hex 32)" \
  REDIS_URL="redis://..." \
  OPENAI_API_KEY="..."            # optional
flyctl deploy
```

## Option C — Render

`render.yaml` is a Blueprint — Render provisions the web service and a managed Redis instance from one file, both on the **free** plan (no card required to start).

```bash
# In the Render dashboard: New -> Blueprint -> point at this repo.
# Render reads render.yaml, provisions agentops + agentops-redis, and
# wires REDIS_URL automatically. You'll be prompted in the dashboard for
# the vars marked `sync: false` (API_KEYS, OPENAI_API_KEY).
```

Free-tier tradeoffs worth knowing before you rely on it for anything but a demo:

- The web service spins down after 15 minutes with no traffic and takes a cold-start hit (several seconds) on the next request — fine for a portfolio demo, not for anything latency-sensitive.
- The free Redis (Key Value) instance is capped at 25 MB / 50 connections — plenty for demo traces and rate-limit counters, not a production cache.
- Upgrading either later is a one-line `plan:` change in `render.yaml`, no re-architecture needed.

---

## What you need to provide

None of the above can be finished by an assistant alone — each requires an account only you hold:

- **A container registry or platform account** (Fly.io / Render / your VPS provider). Sign-up and billing are yours to do.
- **A Redis instance** — either self-hosted (Option A already includes it) or managed (Fly Redis, Render's blueprint, Upstash, Redis Cloud).
- **API keys you generate**, not ones to hand over in chat: `API_KEYS` is something you generate locally (`openssl rand -hex 32`) and paste into your platform's secret manager, not into a conversation.
- **`OPENAI_API_KEY`**, only if you want LLM-backed classification/planning/decomposition instead of the deterministic default — also entered directly into your platform's secret manager.
- **A domain**, if you want one — optional, every platform above gives you a working `*.fly.dev` / `*.onrender.com` URL with no domain needed.

If you're logged into a deploy CLI (`flyctl`, `render`) in this environment already, that changes what's possible — say so and the actual `deploy` command can be run directly instead of just handed to you.
