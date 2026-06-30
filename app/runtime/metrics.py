from prometheus_client import Counter, Histogram

REQUEST_COUNT = Counter(
    "agentops_requests_total",
    "Total number of processed requests",
    ["route", "status"],
)

REQUEST_LATENCY_SECONDS = Histogram(
    "agentops_request_latency_seconds",
    "Request latency",
    ["route"],
)

TOOL_EXECUTION_TOTAL = Counter(
    "agentops_tool_execution_total",
    "Total number of tool executions",
    ["tool_name", "status"],
)

TOOL_EXECUTION_LATENCY_SECONDS = Histogram(
    "agentops_tool_execution_latency_seconds",
    "Tool execution latency",
    ["tool_name"],
)

VERIFIER_ESCALATIONS_TOTAL = Counter(
    "agentops_verifier_escalations_total",
    "Total number of verified intents requiring human escalation",
)

