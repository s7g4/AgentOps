# Observability

## Prometheus Metrics

| Metric | Type | Labels |
|---|---|---|
| `agentops_requests_total` | Counter | `route`, `status` |
| `agentops_request_latency_seconds` | Histogram | `route` |
| `agentops_tool_execution_total` | Counter | `tool_name`, `status` |
| `agentops_tool_execution_latency_seconds` | Histogram | `tool_name` |
| `agentops_verifier_escalations_total` | Counter | — |

## Structured Logging

Every log line is a flat JSON object with `trace_id` injected automatically via `contextvars.ContextVar`:

```json
{
  "timestamp": "2026-07-03T10:00:00.000Z",
  "level": "info",
  "event": "request_received",
  "trace_id": "550e8400-e29b-41d4-...",
  "customer_id": "cust_123"
}
```

## Tracing

Set `OTEL_ENABLED=true` and `OTEL_ENDPOINT` to export per-stage spans (classify/plan/execute/verify) to any OTLP-compatible backend (Jaeger, Tempo, Honeycomb, etc.). `app/telemetry` wraps OpenTelemetry behind a no-op shim, so every `start_as_current_span()` call is a zero-cost context manager when tracing is disabled.

## Execution Traces

Every `/messages` request produces a structured `Trace` in `TraceStore`: state transitions, tool calls, and agent decisions, retrievable via `GET /trace/{trace_id}`.
