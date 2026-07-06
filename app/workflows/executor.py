"""AsyncWorkflowExecutor — topological sort + parallel asyncio.gather execution.

Algorithm
─────────
1. Call definition.execution_layers() → list[list[WorkflowStep]]
   Each layer contains steps that can run concurrently (all their deps
   are in earlier layers).

2. For each layer:
   a. asyncio.gather(*[_execute_step(step) for step in layer])
   b. Persist execution snapshot to the store after the layer.
   c. If any step in the layer failed → mark remaining steps as SKIPPED
      and transition the execution to FAILED.

3. On full completion → transition to COMPLETED.

Step execution
──────────────
Each step:
  - Merges context + step.static_input (context takes precedence for
    explicit overrides, static_input fills the rest).
  - kind="tool": calls ToolRegistry.execute() wrapped in asyncio.to_thread()
    to avoid blocking the event loop on synchronous tool code.
  - kind="agent": posts an AgentMessage on the AgentBus and awaits the reply.
    Agent handlers are already async, so no to_thread() wrapper is needed.
  - Records StepResult with timing. Both kinds produce the same StepResult
    shape, so template resolution ($step.<id>.<key>) doesn't care which
    kind produced an upstream output.

Why asyncio.to_thread for tools but not agents?
────────────────────────────────────────────────
Existing tools (CheckOrderStatusTool, RefundPolicyTool) are synchronous.
Running them directly in the event loop would block all other coroutines
for their duration.  to_thread() runs them in the default thread pool
so the event loop stays responsive.  Agents are async by contract
(RoutableAgent.handle is a coroutine), so they're awaited directly.
"""

from __future__ import annotations

import asyncio
import logging

from app.agents.registry import AgentRegistry
from app.exceptions import WorkflowExecutionError
from app.messaging.bus import AgentBus
from app.messaging.message import AgentMessage
from app.registry.tool_registry import ToolRegistry
from app.schemas.trace import utc_now_iso
from app.workflows.definition import WorkflowDefinition, WorkflowStep
from app.workflows.execution import StepResult, StepStatus, WorkflowExecution, WorkflowStatus
from app.workflows.store import WorkflowStoreProtocol

logger = logging.getLogger(__name__)


class AsyncWorkflowExecutor:
    """Executes a WorkflowDefinition as a layered async DAG.

    Parameters
    ----------
    tool_registry:  Registry for resolving and executing tool-kind steps.
    store:          Persistence store — execution is checkpointed after each layer.
    agent_bus:      Bus for dispatching agent-kind steps. Optional — a workflow
                    with no agent-kind steps never needs one.
    agent_registry: Registry the bus resolves agent-kind step recipients against.
                    Required if agent_bus is provided.
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        store: WorkflowStoreProtocol,
        agent_bus: AgentBus | None = None,
        agent_registry: AgentRegistry | None = None,
    ) -> None:
        self._registry = tool_registry
        self._store = store
        self._agent_bus = agent_bus
        self._agent_registry = agent_registry

    # ── Public API ────────────────────────────────────────────────────────────

    async def run(
        self,
        definition: WorkflowDefinition,
        execution: WorkflowExecution,
    ) -> WorkflowExecution:
        """Execute the workflow and return the final WorkflowExecution.

        The execution is persisted to the store before returning so that
        callers can query status without holding the returned object.
        """
        execution.status = WorkflowStatus.RUNNING
        execution.touch()
        await self._store.put_execution(execution)

        logger.info(
            "workflow_execution_started",
            extra={
                "workflow_id": definition.id,
                "execution_id": execution.execution_id,
                "step_count": len(definition.steps),
            },
        )

        try:
            layers = definition.execution_layers()
        except ValueError as exc:
            execution.status = WorkflowStatus.FAILED
            execution.touch()
            await self._store.put_execution(execution)
            raise WorkflowExecutionError(str(exc)) from exc

        for layer_index, layer in enumerate(layers):
            logger.info(
                "workflow_layer_started",
                extra={
                    "layer": layer_index,
                    "steps": [s.id for s in layer],
                },
            )
            layer_results = await asyncio.gather(
                *[
                    self._execute_step(step, execution.context, execution.step_results)
                    for step in layer
                ],
                return_exceptions=True,
            )

            # Record results and detect failures.
            failed = False
            for step, result in zip(layer, layer_results, strict=True):
                if isinstance(result, StepResult):
                    execution.step_results[step.id] = result
                    if result.status == StepStatus.FAILED:
                        failed = True
                else:
                    # Unexpected exception — wrap it.
                    execution.step_results[step.id] = StepResult(
                        step_id=step.id,
                        status=StepStatus.FAILED,
                        started_at=utc_now_iso(),
                        finished_at=utc_now_iso(),
                        error=str(result),
                    )
                    failed = True

            execution.touch()
            await self._store.put_execution(execution)

            if failed:
                # Mark all remaining (not yet executed) steps as SKIPPED.
                executed_ids = set(execution.step_results)
                for remaining_step in definition.steps:
                    if remaining_step.id not in executed_ids:
                        execution.step_results[remaining_step.id] = StepResult(
                            step_id=remaining_step.id,
                            status=StepStatus.SKIPPED,
                            started_at=utc_now_iso(),
                            finished_at=utc_now_iso(),
                        )

                execution.status = WorkflowStatus.FAILED
                execution.touch()
                await self._store.put_execution(execution)

                logger.warning(
                    "workflow_execution_failed",
                    extra={
                        "workflow_id": definition.id,
                        "execution_id": execution.execution_id,
                        "failed_layer": layer_index,
                    },
                )
                return execution

        execution.status = WorkflowStatus.COMPLETED
        execution.touch()
        await self._store.put_execution(execution)

        logger.info(
            "workflow_execution_completed",
            extra={
                "workflow_id": definition.id,
                "execution_id": execution.execution_id,
            },
        )
        return execution

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _execute_step(
        self,
        step: WorkflowStep,
        context: dict[str, object],
        step_results: dict[str, StepResult],
    ) -> StepResult:
        """Execute a single step and return its StepResult.

        Input resolution: static_input is resolved for templates, then
        context values overlay it (context overrides static defaults).
        """
        from app.workflows.template import resolve_templates  # noqa: PLC0415

        started_at = utc_now_iso()

        try:
            resolved_static = resolve_templates(step.static_input, step_results)
            merged_input: dict[str, object] = {**resolved_static, **context}
        except Exception as exc:  # noqa: BLE001
            finished_at = utc_now_iso()
            logger.warning(
                "workflow_step_template_failed",
                extra={
                    "step_id": step.id,
                    "tool": step.tool_name,
                    "error": str(exc),
                },
            )
            return StepResult(
                step_id=step.id,
                status=StepStatus.FAILED,
                error=str(exc),
                started_at=started_at,
                finished_at=finished_at,
            )

        target = step.tool_name if step.kind == "tool" else step.agent_name
        logger.info(
            "workflow_step_started",
            extra={"step_id": step.id, "kind": step.kind, "target": target},
        )
        try:
            output = await self._dispatch(step, merged_input)
            finished_at = utc_now_iso()
            logger.info(
                "workflow_step_succeeded",
                extra={"step_id": step.id, "kind": step.kind, "target": target},
            )
            return StepResult(
                step_id=step.id,
                status=StepStatus.SUCCESS,
                output=output,
                started_at=started_at,
                finished_at=finished_at,
            )
        except Exception as exc:  # noqa: BLE001
            finished_at = utc_now_iso()
            logger.warning(
                "workflow_step_failed",
                extra={
                    "step_id": step.id,
                    "kind": step.kind,
                    "target": target,
                    "error": str(exc),
                },
            )
            return StepResult(
                step_id=step.id,
                status=StepStatus.FAILED,
                error=str(exc),
                started_at=started_at,
                finished_at=finished_at,
            )

    async def _dispatch(
        self, step: WorkflowStep, merged_input: dict[str, object]
    ) -> dict[str, object]:
        """Execute a single step's tool or agent call and return its raw output."""
        if step.kind == "tool":
            assert step.tool_name is not None  # enforced by WorkflowStep.__post_init__
            return await asyncio.to_thread(self._registry.execute, step.tool_name, merged_input)

        assert step.agent_name is not None  # enforced by WorkflowStep.__post_init__
        if self._agent_bus is None or self._agent_registry is None:
            raise WorkflowExecutionError(
                f"Step {step.id!r} targets agent {step.agent_name!r} but this executor "
                "was not configured with an agent_bus/agent_registry."
            )
        message = AgentMessage(
            sender="workflow_executor", recipient=step.agent_name, payload=merged_input
        )
        reply = await self._agent_bus.send(message, self._agent_registry)
        return reply.payload

