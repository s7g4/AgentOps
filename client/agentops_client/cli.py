"""Command-line interface for the AgentOps API.

Thin wrapper over AgentOpsClient — every command maps to one client call
and prints the result as JSON, so it composes with jq/scripts rather than
inventing its own output format.
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Annotated, Any

import typer

from agentops_client.client import AgentOpsClient
from agentops_client.exceptions import AgentOpsClientError

app = typer.Typer(help="AgentOps API client.", no_args_is_help=True)
workflows_app = typer.Typer(help="Manage and run workflows.", no_args_is_help=True)
agents_app = typer.Typer(help="List agents and route goals.", no_args_is_help=True)
trace_app = typer.Typer(help="Inspect execution traces.", no_args_is_help=True)
app.add_typer(workflows_app, name="workflows")
app.add_typer(agents_app, name="agents")
app.add_typer(trace_app, name="trace")

_BaseUrlOption = Annotated[
    str, typer.Option(envvar="AGENTOPS_BASE_URL", help="AgentOps server URL.")
]
_ApiKeyOption = Annotated[
    str | None, typer.Option(envvar="AGENTOPS_API_KEY", help="X-Api-Key header value.")
]


def _print(value: Any) -> None:  # noqa: ANN401
    if is_dataclass(value) and not isinstance(value, type):
        value = asdict(value)
    elif isinstance(value, list):
        value = [asdict(v) if is_dataclass(v) and not isinstance(v, type) else v for v in value]
    typer.echo(json.dumps(value, indent=2, default=str))


def _client(base_url: str, api_key: str | None) -> AgentOpsClient:
    return AgentOpsClient(base_url=base_url, api_key=api_key)


def _fail(exc: AgentOpsClientError) -> None:
    typer.echo(f"error: {exc}", err=True)
    raise typer.Exit(code=1)


@app.command()
def health(
    base_url: _BaseUrlOption = "http://localhost:8000",
    api_key: _ApiKeyOption = None,
) -> None:
    """Check server health and dependency status."""
    with _client(base_url, api_key) as client:
        try:
            _print(client.health())
        except AgentOpsClientError as exc:
            _fail(exc)


@app.command()
def tools(
    base_url: _BaseUrlOption = "http://localhost:8000",
    api_key: _ApiKeyOption = None,
) -> None:
    """List registered tools."""
    with _client(base_url, api_key) as client:
        try:
            _print(client.list_tools())
        except AgentOpsClientError as exc:
            _fail(exc)


@app.command(name="send")
def send_message(
    message: Annotated[str, typer.Argument(help="Customer message text.")],
    customer_id: Annotated[str, typer.Option(help="Customer identifier.")],
    source: Annotated[str, typer.Option(help="ticket/email/chat/contact_form/other.")] = "other",
    base_url: _BaseUrlOption = "http://localhost:8000",
    api_key: _ApiKeyOption = None,
) -> None:
    """Send a message through the classify/plan/execute/verify/respond pipeline."""
    with _client(base_url, api_key) as client:
        try:
            _print(client.send_message(message=message, customer_id=customer_id, source=source))
        except AgentOpsClientError as exc:
            _fail(exc)


# ── trace ─────────────────────────────────────────────────────────────────────

@trace_app.command(name="get")
def trace_get(
    trace_id: str,
    base_url: _BaseUrlOption = "http://localhost:8000",
    api_key: _ApiKeyOption = None,
) -> None:
    """Fetch a single execution trace."""
    with _client(base_url, api_key) as client:
        try:
            _print(client.get_trace(trace_id))
        except AgentOpsClientError as exc:
            _fail(exc)


@trace_app.command(name="list")
def trace_list(
    limit: int = 20,
    offset: int = 0,
    base_url: _BaseUrlOption = "http://localhost:8000",
    api_key: _ApiKeyOption = None,
) -> None:
    """List recent execution traces."""
    with _client(base_url, api_key) as client:
        try:
            page = client.list_traces(limit=limit, offset=offset)
            _print({"total": page.total, "traces": page.items})
        except AgentOpsClientError as exc:
            _fail(exc)


# ── workflows ─────────────────────────────────────────────────────────────────

@workflows_app.command(name="create")
def workflows_create(
    file: Annotated[Path, typer.Option(help="Path to a JSON workflow definition.")],
    base_url: _BaseUrlOption = "http://localhost:8000",
    api_key: _ApiKeyOption = None,
) -> None:
    """Create a workflow from a JSON file: {"name", "description", "steps"}."""
    spec = json.loads(file.read_text())
    with _client(base_url, api_key) as client:
        try:
            wf = client.create_workflow(
                name=spec["name"], steps=spec["steps"], description=spec.get("description", "")
            )
            _print(wf)
        except AgentOpsClientError as exc:
            _fail(exc)


@workflows_app.command(name="list")
def workflows_list(
    limit: int = 20,
    offset: int = 0,
    base_url: _BaseUrlOption = "http://localhost:8000",
    api_key: _ApiKeyOption = None,
) -> None:
    """List workflow definitions."""
    with _client(base_url, api_key) as client:
        try:
            page = client.list_workflows(limit=limit, offset=offset)
            _print({"total": page.total, "workflows": page.items})
        except AgentOpsClientError as exc:
            _fail(exc)


@workflows_app.command(name="get")
def workflows_get(
    workflow_id: str,
    base_url: _BaseUrlOption = "http://localhost:8000",
    api_key: _ApiKeyOption = None,
) -> None:
    """Fetch a single workflow definition."""
    with _client(base_url, api_key) as client:
        try:
            _print(client.get_workflow(workflow_id))
        except AgentOpsClientError as exc:
            _fail(exc)


@workflows_app.command(name="delete")
def workflows_delete(
    workflow_id: str,
    base_url: _BaseUrlOption = "http://localhost:8000",
    api_key: _ApiKeyOption = None,
) -> None:
    """Delete a workflow definition."""
    with _client(base_url, api_key) as client:
        try:
            client.delete_workflow(workflow_id)
            typer.echo(f"deleted {workflow_id}")
        except AgentOpsClientError as exc:
            _fail(exc)


@workflows_app.command(name="run")
def workflows_run(
    workflow_id: str,
    context_file: Annotated[
        Path | None, typer.Option(help="Path to a JSON context object.")
    ] = None,
    background: Annotated[bool, typer.Option(help="Return immediately; poll for the result.")] = (
        False
    ),
    base_url: _BaseUrlOption = "http://localhost:8000",
    api_key: _ApiKeyOption = None,
) -> None:
    """Run a workflow, optionally in the background."""
    context = json.loads(context_file.read_text()) if context_file else {}
    with _client(base_url, api_key) as client:
        try:
            _print(client.run_workflow(workflow_id, context=context, background=background))
        except AgentOpsClientError as exc:
            _fail(exc)


@workflows_app.command(name="runs")
def workflows_runs(
    workflow_id: str,
    execution_id: Annotated[
        str | None, typer.Option(help="Fetch one execution instead of listing.")
    ] = None,
    limit: int = 20,
    offset: int = 0,
    base_url: _BaseUrlOption = "http://localhost:8000",
    api_key: _ApiKeyOption = None,
) -> None:
    """List a workflow's executions, or fetch one by --execution-id."""
    with _client(base_url, api_key) as client:
        try:
            if execution_id:
                _print(client.get_execution(workflow_id, execution_id))
            else:
                page = client.list_executions(workflow_id, limit=limit, offset=offset)
                _print({"total": page.total, "executions": page.items})
        except AgentOpsClientError as exc:
            _fail(exc)


# ── agents ────────────────────────────────────────────────────────────────────

@agents_app.command(name="list")
def agents_list(
    base_url: _BaseUrlOption = "http://localhost:8000",
    api_key: _ApiKeyOption = None,
) -> None:
    """List registered agents."""
    with _client(base_url, api_key) as client:
        try:
            _print(client.list_agents())
        except AgentOpsClientError as exc:
            _fail(exc)


@agents_app.command(name="route")
def agents_route(
    goal: Annotated[str, typer.Argument(help="Goal to route.")],
    subtasks_file: Annotated[
        Path | None,
        typer.Option(help="JSON list of {agent_name, payload} to dispatch explicitly."),
    ] = None,
    base_url: _BaseUrlOption = "http://localhost:8000",
    api_key: _ApiKeyOption = None,
) -> None:
    """Route a goal — explicitly via --subtasks-file, or through the decomposer."""
    subtasks = json.loads(subtasks_file.read_text()) if subtasks_file else None
    with _client(base_url, api_key) as client:
        try:
            _print(client.route_goal(goal, subtasks=subtasks))
        except AgentOpsClientError as exc:
            _fail(exc)


@agents_app.command(name="routes")
def agents_routes(
    routing_id: Annotated[
        str | None, typer.Option(help="Fetch one routing run instead of listing.")
    ] = None,
    limit: int = 20,
    offset: int = 0,
    base_url: _BaseUrlOption = "http://localhost:8000",
    api_key: _ApiKeyOption = None,
) -> None:
    """List routing run history, or fetch one by --routing-id."""
    with _client(base_url, api_key) as client:
        try:
            if routing_id:
                _print(client.get_routing_run(routing_id))
            else:
                page = client.list_routing_runs(limit=limit, offset=offset)
                _print({"total": page.total, "routes": page.items})
        except AgentOpsClientError as exc:
            _fail(exc)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
