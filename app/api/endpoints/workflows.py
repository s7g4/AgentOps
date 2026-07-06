"""Workflow Engine API endpoints — CRUD + run.

Routes
──────
POST   /workflows                         Create a workflow definition
GET    /workflows                         List definitions (paginated)
GET    /workflows/{workflow_id}           Get a definition
DELETE /workflows/{workflow_id}           Delete a definition
POST   /workflows/{workflow_id}/run       Execute a workflow
GET    /workflows/{workflow_id}/runs      List executions for a workflow
GET    /workflows/{workflow_id}/runs/{execution_id}  Get execution status

Design decisions
────────────────
• Validation (cycle detection, dangling deps) happens at creation time,
  not at run time.  A 422 at creation is far better than a 500 mid-run.
• POST /run returns immediately with the full execution result.
  Workflows execute synchronously within the request because individual
  tool calls are fast (< 1s).  Background execution via task queues
  is a Version 4 concern.
• Pagination uses limit/offset for simplicity and consistency with
  GET /trace/ — cursor-based pagination is deferred to V4.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_workflow_executor, get_workflow_store
from app.exceptions import WorkflowNotFoundError
from app.schemas.workflow import (
    CreateWorkflowRequest,
    ExecutionListResponse,
    ExecutionResponse,
    RunWorkflowRequest,
    StepResultResponse,
    WorkflowListResponse,
    WorkflowResponse,
    WorkflowStepSchema,
)
from app.workflows.definition import WorkflowDefinition, WorkflowStep
from app.workflows.execution import WorkflowExecution
from app.workflows.executor import AsyncWorkflowExecutor
from app.workflows.store import InMemoryWorkflowStore, RedisWorkflowStore

logger = logging.getLogger(__name__)

workflows_router = APIRouter(prefix="/workflows", tags=["workflows"])

# ── Type aliases for DI ───────────────────────────────────────────────────────

WorkflowStore = InMemoryWorkflowStore | RedisWorkflowStore

# Background workflow runs are fire-and-forget asyncio tasks. asyncio only
# holds a *weak* reference to a task once nothing else references it, so
# without this set a task can be garbage-collected mid-run — this set is
# the strong reference that keeps it alive until it completes.
_background_tasks: set[asyncio.Task[WorkflowExecution]] = set()


def _run_in_background(
    executor: AsyncWorkflowExecutor,
    wf: WorkflowDefinition,
    execution: WorkflowExecution,
) -> None:
    task = asyncio.create_task(executor.run(wf, execution))
    _background_tasks.add(task)

    def _on_done(t: asyncio.Task[WorkflowExecution]) -> None:
        _background_tasks.discard(t)
        if t.cancelled():
            return
        if (exc := t.exception()) is not None:
            logger.error(
                "background_workflow_run_failed",
                extra={"execution_id": execution.execution_id, "error": str(exc)},
            )

    task.add_done_callback(_on_done)


def _to_response(wf: WorkflowDefinition) -> WorkflowResponse:
    return WorkflowResponse(
        id=wf.id,
        name=wf.name,
        description=wf.description,
        steps=[
            WorkflowStepSchema(
                id=s.id,
                kind=s.kind,
                tool_name=s.tool_name,
                agent_name=s.agent_name,
                static_input=s.static_input,
                depends_on=s.depends_on,
            )
            for s in wf.steps
        ],
        created_at=wf.created_at,
        updated_at=wf.updated_at,
    )


def _to_execution_response(ex: WorkflowExecution) -> ExecutionResponse:
    return ExecutionResponse(
        execution_id=ex.execution_id,
        workflow_id=ex.workflow_id,
        status=ex.status.value,
        step_results={
            step_id: StepResultResponse(
                step_id=r.step_id,
                status=r.status.value,
                output=r.output,
                error=r.error,
                started_at=r.started_at,
                finished_at=r.finished_at,
            )
            for step_id, r in ex.step_results.items()
        },
        created_at=ex.created_at,
        updated_at=ex.updated_at,
    )


# ── CRUD ──────────────────────────────────────────────────────────────────────

@workflows_router.post(
    "", status_code=201, response_model=WorkflowResponse, summary="Create workflow"
)
async def create_workflow(
    body: CreateWorkflowRequest,
    store: Annotated[WorkflowStore, Depends(get_workflow_store)],
) -> WorkflowResponse:
    """Create and persist a new workflow definition.

    Validates the DAG (duplicate step IDs, dangling deps, cycles) before
    persisting.  Returns 422 if the definition is invalid.
    """
    steps = [
        WorkflowStep(
            id=s.id,
            kind=s.kind,
            tool_name=s.tool_name,
            agent_name=s.agent_name,
            static_input=dict(s.static_input),
            depends_on=list(s.depends_on),
        )
        for s in body.steps
    ]
    wf = WorkflowDefinition(name=body.name, description=body.description, steps=steps)

    try:
        wf.validate()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    await store.put_definition(wf)
    return _to_response(wf)


@workflows_router.get("", response_model=WorkflowListResponse, summary="List workflows")
async def list_workflows(
    store: Annotated[WorkflowStore, Depends(get_workflow_store)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> WorkflowListResponse:
    """Return a paginated list of workflow definitions, most recent first."""
    workflows = await store.list_definitions(limit=limit, offset=offset)
    total = await store.count_definitions()
    return WorkflowListResponse(
        total=total,
        workflows=[_to_response(wf) for wf in workflows],
    )


@workflows_router.get("/{workflow_id}", response_model=WorkflowResponse, summary="Get workflow")
async def get_workflow(
    workflow_id: str,
    store: Annotated[WorkflowStore, Depends(get_workflow_store)],
) -> WorkflowResponse:
    """Retrieve a single workflow definition by ID."""
    wf = await store.get_definition(workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id!r} not found.")
    return _to_response(wf)


@workflows_router.delete("/{workflow_id}", status_code=204, summary="Delete workflow")
async def delete_workflow(
    workflow_id: str,
    store: Annotated[WorkflowStore, Depends(get_workflow_store)],
) -> None:
    """Delete a workflow definition.  Returns 404 if the ID does not exist."""
    deleted = await store.delete_definition(workflow_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id!r} not found.")


# ── Execution ─────────────────────────────────────────────────────────────────

@workflows_router.post(
    "/{workflow_id}/run",
    response_model=ExecutionResponse,
    status_code=200,
    summary="Run workflow",
)
async def run_workflow(
    workflow_id: str,
    body: RunWorkflowRequest,
    store: Annotated[WorkflowStore, Depends(get_workflow_store)],
    executor: Annotated[AsyncWorkflowExecutor, Depends(get_workflow_executor)],
) -> ExecutionResponse:
    """Execute a workflow and return its execution.

    By default the run is synchronous within the request — all steps
    execute before the response is returned. Each tool-kind step runs
    inside asyncio.to_thread() so the event loop is not blocked.

    With ``background=true``, the execution is persisted as PENDING and
    handed to an in-process asyncio task immediately; the caller polls
    GET .../runs/{execution_id} for progress. This is in-process only —
    a run in flight is lost if the process restarts — which is the right
    tradeoff for a single-container deployment; a durable queue is the
    natural upgrade if that stops being true.
    """
    wf = await store.get_definition(workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id!r} not found.")

    execution = WorkflowExecution(
        workflow_id=workflow_id,
        context=dict(body.context),
    )

    if body.background:
        await store.put_execution(execution)
        _run_in_background(executor, wf, execution)
        return _to_execution_response(execution)

    try:
        result = await executor.run(wf, execution)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return _to_execution_response(result)


@workflows_router.get(
    "/{workflow_id}/runs",
    response_model=ExecutionListResponse,
    summary="List workflow runs",
)
async def list_runs(
    workflow_id: str,
    store: Annotated[WorkflowStore, Depends(get_workflow_store)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ExecutionListResponse:
    """Return paginated executions for a workflow, most recent first."""
    wf = await store.get_definition(workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id!r} not found.")

    executions = await store.list_executions(workflow_id, limit=limit, offset=offset)
    total = await store.count_executions(workflow_id)
    return ExecutionListResponse(
        total=total,
        executions=[_to_execution_response(ex) for ex in executions],
    )


@workflows_router.get(
    "/{workflow_id}/runs/{execution_id}",
    response_model=ExecutionResponse,
    summary="Get run status",
)
async def get_run(
    workflow_id: str,
    execution_id: str,
    store: Annotated[WorkflowStore, Depends(get_workflow_store)],
) -> ExecutionResponse:
    """Retrieve a single execution by ID."""
    ex = await store.get_execution(execution_id)
    if ex is None or ex.workflow_id != workflow_id:
        raise HTTPException(
            status_code=404,
            detail=f"Execution {execution_id!r} not found for workflow {workflow_id!r}.",
        )
    return _to_execution_response(ex)


# Suppress unused import — imported for re-export/type checking only.
_ = WorkflowNotFoundError
