# Security Policy

## Reporting a vulnerability

Open a [GitHub Security Advisory](../../security/advisories/new) on this repository rather than a public issue — that's the standard private-disclosure channel and keeps details out of public view until a fix ships. If that isn't available to you, open an issue titled "security" with no details and ask for a private contact; do not post exploit details in a public issue.

Include: affected version/commit, a minimal reproduction, and the impact you think it has. A response should follow within a few days.

## Supported versions

Only the latest `1.x` release is supported. There's no LTS branch at this stage.

## What's in scope

- Authentication and rate-limiting middleware (`app/middleware/`)
- Anything that constructs a Redis key, SQL-adjacent query, or shell command from request input
- Deserialization of persisted state (trace/workflow/routing stores)

## What's explicitly out of scope

- Findings that require `AUTH_ENABLED=false` (the local-development default) in a deployment you control — that flag exists precisely so you can choose to require auth in production; running without it and then reporting "no auth" isn't a vulnerability in the software.
- Denial of service via raw request volume against an instance with no rate limiting configured, for the same reason.
- Vulnerabilities in third-party dependencies — report those upstream; we'll pick up the fix via a version bump once one's available.
