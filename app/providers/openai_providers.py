"""OpenAI-backed async provider implementations.

Design decisions
────────────────
1. **Structured outputs / JSON mode** for classification and verification.
   We use ``response_format={"type": "json_object"}`` + a system prompt that
   mandates JSON.  This is cheaper and more reliable than asking the model to
   produce structured YAML or parsing freeform text with regex.

2. **Function calling for planning**.
   The planner uses the OpenAI tool-calling API, passing ToolRegistry tool
   schemas as ``tools``.  The model picks which tools to call and with what
   inputs.  This is far more flexible than hardcoded keyword matching.

3. **gpt-4o-mini as default**.
   Cost-effective for classification / verification.  Override via
   ``OPENAI_MODEL`` env var for tasks that need stronger reasoning.

4. **Fail-fast on missing key**.
   Every provider raises ``ConfigurationError`` at instantiation (not at call
   time) if ``OPENAI_API_KEY`` is absent.  This prevents silent failures that
   surface only under load.

5. **Typed error mapping**.
   OpenAI API errors (auth, rate limit, server) are mapped to AgentOps
   exceptions so middleware can return correct HTTP status codes without
   knowing about OpenAI internals.
"""

from __future__ import annotations

import json
import logging
from typing import Any, cast

from openai import APIStatusError, AsyncOpenAI, AuthenticationError
from openai import RateLimitError as OpenAIRateLimitError
from openai.types.chat import ChatCompletionToolParam

from app.exceptions import (
    AgentOpsError,
    ClassificationError,
    ConfigurationError,
    PlanningError,
    RateLimitError,
    VerificationError,
)
from app.providers.base import (
    AsyncClassificationProvider,
    AsyncPlanningProvider,
    AsyncResponseProvider,
    AsyncVerificationProvider,
)
from app.schemas.classification import Classification
from app.schemas.plan import ToolPlan
from app.schemas.verification import VerificationResult

logger = logging.getLogger(__name__)

_CLASSIFICATION_SYSTEM = """You are a customer-support intent classifier.

Classify the customer message into EXACTLY ONE of these intents:
  - refund          (customer wants money back or a refund)
  - order_status    (customer asking about order tracking / delivery)
  - spam            (unsolicited / irrelevant message)
  - general_question (anything else)

Respond with ONLY a JSON object, nothing else:
{"intent": "<intent>", "confidence": <float between 0.0 and 1.0>}"""

_VERIFICATION_SYSTEM = """You are a quality-control agent reviewing an AI customer-support response.

Given the original customer message, the detected intent, and tool outputs, decide:
1. Is the response factually grounded in the tool outputs?
2. Is the confidence appropriate?
3. Should this be escalated to a human?

Respond with ONLY a JSON object:
{"confidence": <float 0-1>, "escalated": <true|false>, "reason": "<brief reason or null>"}"""

_RESPONSE_SYSTEM = """You are a helpful, professional customer-support agent.
Write a concise, empathetic response to the customer using the provided context.
Do NOT mention internal tools, systems, or AI. Keep replies under 3 sentences."""


def _make_client(api_key: str | None) -> AsyncOpenAI:
    if not api_key:
        raise ConfigurationError(
            "OPENAI_API_KEY is required to use OpenAI providers. "
            "Set it in your environment or .env file."
        )
    return AsyncOpenAI(api_key=api_key)


def _map_openai_error(exc: Exception, context: str) -> AgentOpsError:
    """Map OpenAI SDK errors to AgentOps typed exceptions."""
    if isinstance(exc, AuthenticationError):
        return ConfigurationError(f"OpenAI auth failed during {context}: {exc}")
    if isinstance(exc, OpenAIRateLimitError):
        return RateLimitError(f"OpenAI rate limit exceeded during {context}")
    if isinstance(exc, APIStatusError):
        return AgentOpsError(f"OpenAI API error during {context}: {exc.status_code} {exc.message}")
    return AgentOpsError(f"Unexpected OpenAI error during {context}: {exc}")


class OpenAIClassificationProvider(AsyncClassificationProvider):
    """Classify customer messages using chat completions with JSON mode."""

    def __init__(self, api_key: str | None, model: str = "gpt-4o-mini") -> None:
        self._client = _make_client(api_key)
        self._model = model

    async def classify(self, message: str) -> Classification:
        try:
            resp = await self._client.chat.completions.create(
                model=self._model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": _CLASSIFICATION_SYSTEM},
                    {"role": "user", "content": message},
                ],
                temperature=0.0,
                max_tokens=64,
            )
        except Exception as exc:
            raise _map_openai_error(exc, "classification") from exc

        raw = resp.choices[0].message.content or "{}"
        try:
            data = json.loads(raw)
            return Classification(
                intent=str(data.get("intent", "general_question")),
                confidence=float(data.get("confidence", 0.5)),
            )
        except (json.JSONDecodeError, ValueError) as exc:
            raise ClassificationError(f"OpenAI returned unparseable JSON: {raw!r}") from exc


class OpenAIPlanningProvider(AsyncPlanningProvider):
    """Produce tool plans using OpenAI function/tool calling.

    Dynamically builds the tool schema from the ToolRegistry so the planner
    always reflects the current registered tools — no hardcoded lists.
    """

    def __init__(
        self,
        api_key: str | None,
        tool_schemas: list[dict[str, Any]],
        model: str = "gpt-4o-mini",
    ) -> None:
        self._client = _make_client(api_key)
        self._tool_schemas = tool_schemas
        self._model = model

    async def plan(self, intent: str, message: str) -> ToolPlan:
        if not self._tool_schemas:
            return ToolPlan(tool_calls=[])

        system = (
            f"You are a tool-selection agent. Intent: {intent}.\n"
            "Select the appropriate tools to answer the customer. "
            "Only call tools that are directly relevant."
        )
        tools_cast = [cast(ChatCompletionToolParam, t) for t in self._tool_schemas]
        try:
            resp = await self._client.chat.completions.create(
                model=self._model,
                tools=tools_cast,
                tool_choice="auto",
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": message},
                ],
                temperature=0.0,
            )
        except Exception as exc:
            raise _map_openai_error(exc, "planning") from exc

        tool_calls: list[dict[str, object]] = []
        msg = resp.choices[0].message
        if msg.tool_calls:
            for tc in msg.tool_calls:
                function = getattr(tc, "function", None)
                if function is None:
                    continue
                try:
                    raw_input = json.loads(function.arguments)
                except json.JSONDecodeError as exc:
                    raise PlanningError(
                        f"Tool call arguments are not valid JSON: {function.arguments!r}"
                    ) from exc
                tool_calls.append({"tool_name": function.name, "input": raw_input})

        return ToolPlan(tool_calls=tool_calls)


class OpenAIVerificationProvider(AsyncVerificationProvider):
    """Verify response quality using a secondary LLM pass."""

    def __init__(self, api_key: str | None, model: str = "gpt-4o-mini") -> None:
        self._client = _make_client(api_key)
        self._model = model

    async def verify(
        self,
        intent: str,
        tool_outputs: list[dict[str, object]],
        original_message: str,
    ) -> VerificationResult:
        context = json.dumps(
            {"intent": intent, "tool_outputs": tool_outputs, "message": original_message},
            indent=2,
        )
        try:
            resp = await self._client.chat.completions.create(
                model=self._model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": _VERIFICATION_SYSTEM},
                    {"role": "user", "content": context},
                ],
                temperature=0.0,
                max_tokens=128,
            )
        except Exception as exc:
            raise _map_openai_error(exc, "verification") from exc

        raw = resp.choices[0].message.content or "{}"
        try:
            data = json.loads(raw)
            return VerificationResult(
                confidence=float(data.get("confidence", 0.5)),
                escalated=bool(data.get("escalated", False)),
                needs_human_reason=data.get("reason"),
            )
        except (json.JSONDecodeError, ValueError) as exc:
            raise VerificationError(
                f"OpenAI returned unparseable verification JSON: {raw!r}"
            ) from exc


class OpenAIResponseProvider(AsyncResponseProvider):
    """Generate a customer-facing response via chat completions."""

    def __init__(self, api_key: str | None, model: str = "gpt-4o-mini") -> None:
        self._client = _make_client(api_key)
        self._model = model

    async def generate(
        self,
        intent: str,
        tool_outputs: list[dict[str, object]],
        original_message: str,
    ) -> str:
        context = (
            f"Customer message: {original_message}\n"
            f"Detected intent: {intent}\n"
            f"Tool results: {json.dumps(tool_outputs, indent=2)}"
        )
        try:
            resp = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": _RESPONSE_SYSTEM},
                    {"role": "user", "content": context},
                ],
                temperature=0.3,
                max_tokens=256,
            )
        except Exception as exc:
            raise _map_openai_error(exc, "response generation") from exc

        return (resp.choices[0].message.content or "").strip()
