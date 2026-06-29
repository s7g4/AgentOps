"""AgentOps async runtime orchestrator.

Why async?
──────────
The sync runtime (V1) serialises all work on a single thread.  One slow LLM
call (p50 ~500ms for gpt-4o-mini) blocks every other in-flight request.
With ``async def handle_message``:

• FastAPI's event loop can interleave I/O waits across thousands of
  concurrent requests without extra threads.
• Multiple tool calls within a single request run in parallel via
  ``asyncio.gather``, reducing wall-clock time proportionally.
• ``handle_batch`` processes all messages concurrently, not sequentially.

Tool execution uses ``asyncio.to_thread`` so that synchronous tool code
(which may do blocking DB/HTTP calls) doesn't stall the event loop.
"""

from __future__ import annotations

import asyncio
import time
import uuid

from tenacity import retry, stop_after_attempt, wait_fixed

from app.agents.classifier.classifier_agent import ClassifierAgent
from app.agents.planner.planner_agent import PlannerAgent
from app.agents.response_generator.response_generator_agent import ResponseGeneratorAgent
from app.agents.verifier.verifier_agent import VerifierAgent
from app.config.settings import load_settings
from app.exceptions import ToolError
from app.logging.structured_logger import bind_trace_id, configure_structlog, get_logger, reset_trace_id
from app.registry.tool_registry import ToolRegistry
from app.runtime.metrics import (
    REQUEST_COUNT,
    REQUEST_LATENCY_SECONDS,
    TOOL_EXECUTION_LATENCY_SECONDS,
    TOOL_EXECUTION_TOTAL,
    VERIFIER_ESCALATIONS_TOTAL,
)
from app.runtime.state_machine import RuntimeState, validate_transition
from app.runtime.trace_store import TraceStore
from app.schemas.messages import BatchRequest, BatchResponse, MessageRequest, MessageResponse
from app.schemas.trace import AgentDecision, ToolCall, Trace, TraceEvent, utc_now_iso

settings = load_settings()
configure_structlog(log_level=settings.log_level)
logger = get_logger()


class AgentOpsRuntime:
    """Async FSM-driven orchestrator.

    Dependency-injected: every collaborator is an interface, not a
    concrete class.  Swap any agent's provider without touching the runtime.
    """

    def __init__(
        self,
        classifier: ClassifierAgent,
        planner: PlannerAgent,
        verifier: VerifierAgent,
        responder: ResponseGeneratorAgent,
        tool_registry: ToolRegistry,
        trace_store: TraceStore,
    ) -> None:
        self.classifier = classifier
        self.planner = planner
        self.verifier = verifier
        self.responder = responder
        self.tool_registry = tool_registry
        self.trace_store = trace_store

    @classmethod
    def default(cls) -> AgentOpsRuntime:
        return cls(
            classifier=ClassifierAgent(),
            planner=PlannerAgent(),
            verifier=VerifierAgent(),
            responder=ResponseGeneratorAgent(),
            tool_registry=ToolRegistry.default(),
            trace_store=TraceStore.default(),
        )

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _record(self, trace: Trace, name: str, data: dict[str, object]) -> None:
        trace.timeline.append(TraceEvent(timestamp=utc_now_iso(), name=name, data=data))

    def _transition(
        self,
        trace: Trace,
        current: RuntimeState,
        to_state: RuntimeState,
    ) -> RuntimeState:
        """Validate and record a state transition. Returns the new state."""
        validate_transition(current, to_state)
        logger.info("state_transition", from_state=current.value, to_state=to_state.value)
        self._record(
            trace,
            f"state:{to_state.value.lower()}",
            {
                "trace_id": trace.trace_id,
                "from": current.value,
                "to": to_state.value,
                "duration_ms": 0.0,
            },
        )
        return to_state

    @retry(stop=stop_after_attempt(2), wait=wait_fixed(0.2), reraise=True)
    def _execute_tool_sync(
        self, tool_name: str, raw_input: dict[str, object]
    ) -> dict[str, object]:
        """Synchronous tool execution wrapped by tenacity retry."""
        start = time.perf_counter()
        status = "success"
        try:
            return self.tool_registry.execute(tool_name, raw_input)
        except Exception:
            status = "error"
            raise
        finally:
            TOOL_EXECUTION_TOTAL.labels(tool_name=tool_name, status=status).inc()
            TOOL_EXECUTION_LATENCY_SECONDS.labels(tool_name=tool_name).observe(
                time.perf_counter() - start
            )

    async def _execute_tool(
        self, tool_name: str, raw_input: dict[str, object]
    ) -> dict[str, object]:
        """Run a synchronous tool in a thread pool to avoid blocking the event loop."""
        return await asyncio.to_thread(self._execute_tool_sync, tool_name, raw_input)

    # ── Core message handler ──────────────────────────────────────────────────

    async def handle_message(self, req: MessageRequest) -> MessageResponse:
        start = time.perf_counter()
        trace_id = str(uuid.uuid4())
        trace = Trace(trace_id=trace_id)
        state = RuntimeState.RECEIVED

        token = bind_trace_id(trace_id)
        try:
            # Record initial RECEIVED state.
            self._record(
                trace,
                "state:received",
                {
                    "trace_id": trace_id,
                    "from": None,
                    "to": RuntimeState.RECEIVED.value,
                    "duration_ms": 0.0,
                },
            )
            self._record(
                trace, "request", {"customer_id": req.customer_id, "source": req.source}
            )
            logger.info("request_received", customer_id=req.customer_id, source=req.source)

            # ── CLASSIFY ──────────────────────────────────────────────────────
            state = self._transition(trace, state, RuntimeState.CLASSIFIED)
            classification = await self.classifier.classify(req.message)
            trace.agent_decisions.append(
                AgentDecision(
                    agent="classifier",
                    summary=f"intent={classification.intent}",
                    data={
                        "intent": classification.intent,
                        "confidence": classification.confidence,
                    },
                )
            )

            # ── PLAN ──────────────────────────────────────────────────────────
            state = self._transition(trace, state, RuntimeState.PLANNING)
            logger.info("planning_started", intent=classification.intent)
            plan = await self.planner.plan(classification.intent, req.message)
            self._record(trace, "plan", {"tool_calls": plan.tool_calls})

            # ── TOOL EXECUTION (parallel) ─────────────────────────────────────
            state = self._transition(trace, state, RuntimeState.TOOL_EXECUTION)
            logger.info("tool_execution_started", tool_count=len(plan.tool_calls))

            tool_outputs: list[dict[str, object]] = []

            if plan.tool_calls:
                results = await asyncio.gather(
                    *[
                        self._execute_tool(call["tool_name"], call["input"])
                        for call in plan.tool_calls
                    ],
                    return_exceptions=True,
                )
                for call, result in zip(plan.tool_calls, results, strict=True):
                    tool_name = call["tool_name"]
                    raw_input = call["input"]
                    if isinstance(result, BaseException):
                        trace.tool_calls.append(
                            ToolCall(
                                tool_name=tool_name,
                                input=raw_input,
                                output=None,
                                error=str(result),
                                status="error",
                            )
                        )
                        self._record(
                            trace,
                            "tool_execution",
                            {"tool_name": tool_name, "status": "error", "error": str(result)},
                        )
                        # Re-raise first tool error to trigger FAILED path.
                        raise result  # type: ignore[misc]
                    else:
                        tool_outputs.append(result)
                        trace.tool_calls.append(
                            ToolCall(
                                tool_name=tool_name,
                                input=raw_input,
                                output=result,
                                error=None,
                                status="success",
                            )
                        )
                        self._record(
                            trace,
                            "tool_execution",
                            {"tool_name": tool_name, "status": "success"},
                        )

            # ── VERIFY ────────────────────────────────────────────────────────
            state = self._transition(trace, state, RuntimeState.VERIFYING)
            logger.info("verification_started")
            verification = await self.verifier.verify(
                classification.intent, tool_outputs, req.message
            )
            trace.agent_decisions.append(
                AgentDecision(
                    agent="verifier",
                    summary=(
                        f"confidence={verification.confidence},"
                        f" escalated={verification.escalated}"
                    ),
                    data={
                        "confidence": verification.confidence,
                        "escalated": verification.escalated,
                    },
                )
            )
            if verification.escalated:
                VERIFIER_ESCALATIONS_TOTAL.inc()

            # ── COMPLETE ──────────────────────────────────────────────────────
            state = self._transition(trace, state, RuntimeState.COMPLETED)
            logger.info("request_completed", escalated=verification.escalated)

            self._record(
                trace,
                "verification_summary",
                {"confidence": verification.confidence, "escalated": verification.escalated},
            )
            tool_success = sum(1 for tc in trace.tool_calls if tc.status == "success")
            tool_error = sum(1 for tc in trace.tool_calls if tc.status == "error")
            self._record(trace, "tools_summary", {"success": tool_success, "error": tool_error})

            final_response_text = await self.responder.generate(
                classification.intent, tool_outputs, req.message
            )
            trace.final_response = {
                "intent": classification.intent,
                "confidence": verification.confidence,
                "escalated": verification.escalated,
                "response": final_response_text,
            }
            await self.trace_store.put(trace)

            REQUEST_COUNT.labels(route="/messages", status="ok").inc()
            REQUEST_LATENCY_SECONDS.labels(route="/messages").observe(
                time.perf_counter() - start
            )
            return MessageResponse(
                trace_id=trace_id,
                intent=classification.intent,
                confidence=verification.confidence,
                escalated=verification.escalated,
                response=final_response_text,
            )

        except Exception as e:  # noqa: BLE001
            # Transition to FAILED from whatever state we're in.
            logger.warning("request_failed", error=str(e), error_type=type(e).__name__)
            self._record(
                trace,
                "state:failed",
                {
                    "trace_id": trace_id,
                    "from": state.value,
                    "to": RuntimeState.FAILED.value,
                    "duration_ms": 0.0,
                },
            )
            self._record(trace, "error", {"error": str(e), "type": type(e).__name__})
            trace.final_response = {"error": str(e)}
            await self.trace_store.put(trace)

            REQUEST_COUNT.labels(route="/messages", status="failed").inc()
            REQUEST_LATENCY_SECONDS.labels(route="/messages").observe(
                time.perf_counter() - start
            )
            return MessageResponse(
                trace_id=trace_id,
                intent="unknown",
                confidence=0.0,
                escalated=True,
                response="Request failed; escalation required.",
            )
        finally:
            reset_trace_id(token)

    async def handle_batch(self, req: BatchRequest) -> BatchResponse:
        """Process all messages concurrently using asyncio.gather.

        Under a sync runtime, batch throughput was bounded by the slowest
        message.  With gather, all messages begin simultaneously and
        wall-clock time approaches max(individual_latencies) rather than
        sum(individual_latencies).
        """
        results = await asyncio.gather(
            *[self.handle_message(m) for m in req.messages]
        )
        return BatchResponse(results=list(results))
