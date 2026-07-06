"""HTTP client for the AgentOps API.

Design
──────
AsyncAgentOpsClient is the real implementation. AgentOpsClient is a thin
sync wrapper that runs each call through asyncio.run() — correct for a CLI
or script where every call is its own short-lived event loop, wrong for a
long-running async application, which should use AsyncAgentOpsClient
directly instead.

The transport parameter exists so tests (and anything else embedding the
server in the same process) can point the client at an ASGI app directly
via httpx.ASGITransport, with no live server or network involved.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from types import TracebackType
from typing import Any, TypeVar

import httpx

from agentops_client.exceptions import AgentOpsHTTPError
from agentops_client.models import (
    AgentInfo,
    Execution,
    HealthStatus,
    MessageResult,
    Page,
    RoutingResult,
    Workflow,
)

T = TypeVar("T")


class AsyncAgentOpsClient:
    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        api_key: str | None = None,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        headers = {"X-Api-Key": api_key} if api_key else {}
        self._client = httpx.AsyncClient(
            base_url=base_url, headers=headers, timeout=timeout, transport=transport
        )

    async def __aenter__(self) -> AsyncAgentOpsClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        response = await self._client.request(method, url, **kwargs)
        if response.status_code >= 400:
            detail = response.text
            try:
                detail = response.json().get("detail", detail)
            except ValueError:
                pass
            raise AgentOpsHTTPError(response.status_code, detail)
        result: dict[str, Any] = response.json() if response.content else {}
        return result

    # ── Health / tools ────────────────────────────────────────────────────────

    async def health(self) -> HealthStatus:
        return HealthStatus.from_dict(await self._request("GET", "/health"))

    async def list_tools(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/tools")
        tools: list[dict[str, Any]] = data["tools"]
        return tools

    # ── Messages ──────────────────────────────────────────────────────────────

    async def send_message(
        self, *, message: str, customer_id: str, source: str = "other"
    ) -> MessageResult:
        body = {"message": message, "customer_id": customer_id, "source": source}
        return MessageResult.from_dict(await self._request("POST", "/messages", json=body))

    # ── Traces ────────────────────────────────────────────────────────────────

    async def get_trace(self, trace_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/trace/{trace_id}")

    async def list_traces(self, limit: int = 20, offset: int = 0) -> Page:
        data = await self._request(
            "GET", "/trace/", params={"limit": limit, "offset": offset}
        )
        return Page(total=data["total"], items=data["traces"])

    # ── Workflows ─────────────────────────────────────────────────────────────

    async def create_workflow(
        self, name: str, steps: list[dict[str, Any]], description: str = ""
    ) -> Workflow:
        body = {"name": name, "description": description, "steps": steps}
        return Workflow.from_dict(await self._request("POST", "/workflows", json=body))

    async def get_workflow(self, workflow_id: str) -> Workflow:
        return Workflow.from_dict(await self._request("GET", f"/workflows/{workflow_id}"))

    async def list_workflows(self, limit: int = 20, offset: int = 0) -> Page:
        data = await self._request(
            "GET", "/workflows", params={"limit": limit, "offset": offset}
        )
        return Page(total=data["total"], items=[Workflow.from_dict(w) for w in data["workflows"]])

    async def delete_workflow(self, workflow_id: str) -> None:
        await self._request("DELETE", f"/workflows/{workflow_id}")

    async def run_workflow(
        self,
        workflow_id: str,
        context: dict[str, Any] | None = None,
        background: bool = False,
    ) -> Execution:
        body = {"context": context or {}, "background": background}
        data = await self._request("POST", f"/workflows/{workflow_id}/run", json=body)
        return Execution.from_dict(data)

    async def get_execution(self, workflow_id: str, execution_id: str) -> Execution:
        data = await self._request("GET", f"/workflows/{workflow_id}/runs/{execution_id}")
        return Execution.from_dict(data)

    async def list_executions(self, workflow_id: str, limit: int = 20, offset: int = 0) -> Page:
        data = await self._request(
            "GET", f"/workflows/{workflow_id}/runs", params={"limit": limit, "offset": offset}
        )
        items = [Execution.from_dict(e) for e in data["executions"]]
        return Page(total=data["total"], items=items)

    # ── Agents / routing ──────────────────────────────────────────────────────

    async def list_agents(self) -> list[AgentInfo]:
        data = await self._request("GET", "/agents")
        return [AgentInfo(**a) for a in data["agents"]]

    async def route_goal(
        self, goal: str, subtasks: list[dict[str, Any]] | None = None
    ) -> RoutingResult:
        body: dict[str, Any] = {"goal": goal}
        if subtasks is not None:
            body["subtasks"] = subtasks
        return RoutingResult.from_dict(await self._request("POST", "/agents/route", json=body))

    async def list_routing_runs(self, limit: int = 20, offset: int = 0) -> Page:
        data = await self._request(
            "GET", "/agents/routes", params={"limit": limit, "offset": offset}
        )
        items = [RoutingResult.from_dict(r) for r in data["routes"]]
        return Page(total=data["total"], items=items)

    async def get_routing_run(self, routing_id: str) -> RoutingResult:
        data = await self._request("GET", f"/agents/routes/{routing_id}")
        return RoutingResult.from_dict(data)


class AgentOpsClient:
    """Synchronous wrapper around AsyncAgentOpsClient — see module docstring.

    Each call opens its own AsyncAgentOpsClient (and thus its own httpx
    connection) inside a single asyncio.run() and closes it before
    returning. httpx.AsyncClient ties its connections to the event loop
    they were first used on — holding one instance across multiple
    asyncio.run() calls (each of which creates a *new* loop) breaks on the
    second call with "Event loop is closed". Paying for a fresh connection
    per call is the right tradeoff here: a CLI invocation makes one or two
    calls and exits, it never needed connection reuse in the first place.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        api_key: str | None = None,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url
        self._api_key = api_key
        self._timeout = timeout
        self._transport = transport

    def __enter__(self) -> AgentOpsClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        pass

    def _run(self, call: Callable[[AsyncAgentOpsClient], Awaitable[T]]) -> T:
        async def _runner() -> T:
            async with AsyncAgentOpsClient(
                base_url=self._base_url,
                api_key=self._api_key,
                timeout=self._timeout,
                transport=self._transport,
            ) as client:
                return await call(client)

        return asyncio.run(_runner())

    def health(self) -> HealthStatus:
        return self._run(lambda c: c.health())

    def list_tools(self) -> list[dict[str, Any]]:
        return self._run(lambda c: c.list_tools())

    def send_message(
        self, *, message: str, customer_id: str, source: str = "other"
    ) -> MessageResult:
        return self._run(
            lambda c: c.send_message(message=message, customer_id=customer_id, source=source)
        )

    def get_trace(self, trace_id: str) -> dict[str, Any]:
        return self._run(lambda c: c.get_trace(trace_id))

    def list_traces(self, limit: int = 20, offset: int = 0) -> Page:
        return self._run(lambda c: c.list_traces(limit=limit, offset=offset))

    def create_workflow(
        self, name: str, steps: list[dict[str, Any]], description: str = ""
    ) -> Workflow:
        return self._run(lambda c: c.create_workflow(name, steps, description))

    def get_workflow(self, workflow_id: str) -> Workflow:
        return self._run(lambda c: c.get_workflow(workflow_id))

    def list_workflows(self, limit: int = 20, offset: int = 0) -> Page:
        return self._run(lambda c: c.list_workflows(limit=limit, offset=offset))

    def delete_workflow(self, workflow_id: str) -> None:
        self._run(lambda c: c.delete_workflow(workflow_id))

    def run_workflow(
        self,
        workflow_id: str,
        context: dict[str, Any] | None = None,
        background: bool = False,
    ) -> Execution:
        return self._run(
            lambda c: c.run_workflow(workflow_id, context=context, background=background)
        )

    def get_execution(self, workflow_id: str, execution_id: str) -> Execution:
        return self._run(lambda c: c.get_execution(workflow_id, execution_id))

    def list_executions(self, workflow_id: str, limit: int = 20, offset: int = 0) -> Page:
        return self._run(lambda c: c.list_executions(workflow_id, limit=limit, offset=offset))

    def list_agents(self) -> list[AgentInfo]:
        return self._run(lambda c: c.list_agents())

    def route_goal(
        self, goal: str, subtasks: list[dict[str, Any]] | None = None
    ) -> RoutingResult:
        return self._run(lambda c: c.route_goal(goal, subtasks=subtasks))

    def list_routing_runs(self, limit: int = 20, offset: int = 0) -> Page:
        return self._run(lambda c: c.list_routing_runs(limit=limit, offset=offset))

    def get_routing_run(self, routing_id: str) -> RoutingResult:
        return self._run(lambda c: c.get_routing_run(routing_id))
