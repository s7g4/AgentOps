"""Workflow persistence store.

Two implementations, same Protocol interface:

  InMemoryWorkflowStore  — default, zero deps, for tests and local dev.
  RedisWorkflowStore     — production, selected via TRACE_BACKEND=redis.

Both stores handle two separate namespaces:
  • Definitions — permanent (no TTL).  Deleted explicitly via DELETE /workflows/{id}.
  • Executions  — expire after 30 days (configurable).

Redis key layout
────────────────
  agentops:workflow:{id}           → JSON-serialised WorkflowDefinition
  agentops:workflows:index         → sorted set, score=created_at unix ts, member=id
  agentops:execution:{id}          → JSON-serialised WorkflowExecution
  agentops:executions:{workflow_id} → sorted set of execution IDs for a workflow
"""

from __future__ import annotations

import json
import time
from threading import RLock
from typing import Protocol, runtime_checkable

from app.workflows.definition import WorkflowDefinition
from app.workflows.execution import WorkflowExecution

_EXEC_TTL = 30 * 24 * 3600  # 30 days


# ── Protocol ──────────────────────────────────────────────────────────────────

@runtime_checkable
class WorkflowStoreProtocol(Protocol):
    """Structural protocol satisfied by all workflow store implementations."""

    async def put_definition(self, wf: WorkflowDefinition) -> None: ...
    async def get_definition(self, wf_id: str) -> WorkflowDefinition | None: ...
    async def list_definitions(self, limit: int, offset: int) -> list[WorkflowDefinition]: ...
    async def count_definitions(self) -> int: ...
    async def delete_definition(self, wf_id: str) -> bool: ...

    async def put_execution(self, ex: WorkflowExecution) -> None: ...
    async def get_execution(self, exec_id: str) -> WorkflowExecution | None: ...
    async def list_executions(
        self, wf_id: str, limit: int, offset: int
    ) -> list[WorkflowExecution]: ...
    async def count_executions(self, wf_id: str) -> int: ...


# ── In-Memory ─────────────────────────────────────────────────────────────────

class InMemoryWorkflowStore:
    """Thread-safe in-memory store for tests and local development."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._definitions: dict[str, WorkflowDefinition] = {}
        # Insertion-order list for deterministic pagination.
        self._def_order: list[str] = []
        self._executions: dict[str, WorkflowExecution] = {}
        # Map workflow_id → ordered list of execution IDs.
        self._exec_index: dict[str, list[str]] = {}

    # ── Definitions ──────────────────────────────────────────────────────────

    async def put_definition(self, wf: WorkflowDefinition) -> None:
        with self._lock:
            if wf.id not in self._definitions:
                self._def_order.append(wf.id)
            self._definitions[wf.id] = wf

    async def get_definition(self, wf_id: str) -> WorkflowDefinition | None:
        with self._lock:
            return self._definitions.get(wf_id)

    async def list_definitions(self, limit: int = 20, offset: int = 0) -> list[WorkflowDefinition]:
        with self._lock:
            ordered = list(reversed(self._def_order))
            page = ordered[offset : offset + limit]
            return [self._definitions[i] for i in page if i in self._definitions]

    async def count_definitions(self) -> int:
        with self._lock:
            return len(self._definitions)

    async def delete_definition(self, wf_id: str) -> bool:
        with self._lock:
            if wf_id not in self._definitions:
                return False
            del self._definitions[wf_id]
            self._def_order = [i for i in self._def_order if i != wf_id]
            return True

    # ── Executions ───────────────────────────────────────────────────────────

    async def put_execution(self, ex: WorkflowExecution) -> None:
        with self._lock:
            is_new = ex.execution_id not in self._executions
            self._executions[ex.execution_id] = ex
            if is_new:
                self._exec_index.setdefault(ex.workflow_id, []).append(ex.execution_id)

    async def get_execution(self, exec_id: str) -> WorkflowExecution | None:
        with self._lock:
            return self._executions.get(exec_id)

    async def list_executions(
        self, wf_id: str, limit: int = 20, offset: int = 0
    ) -> list[WorkflowExecution]:
        with self._lock:
            ids = list(reversed(self._exec_index.get(wf_id, [])))
            page = ids[offset : offset + limit]
            return [self._executions[i] for i in page if i in self._executions]

    async def count_executions(self, wf_id: str) -> int:
        with self._lock:
            return len(self._exec_index.get(wf_id, []))


# ── Redis ─────────────────────────────────────────────────────────────────────

class RedisWorkflowStore:
    """Redis-backed workflow store for production deployments.

    Key layout:
      agentops:workflow:{id}            — definition JSON (no TTL)
      agentops:workflows:index          — sorted set (score=ts, member=id)
      agentops:execution:{id}           — execution JSON (TTL=30d)
      agentops:executions:{workflow_id} — sorted set (score=ts, member=exec_id)
    """

    _WF_PREFIX = "agentops:workflow:"
    _WF_INDEX = "agentops:workflows:index"
    _EX_PREFIX = "agentops:execution:"
    _EX_INDEX_PREFIX = "agentops:executions:"

    def __init__(self, redis_url: str, exec_ttl_seconds: int = _EXEC_TTL) -> None:
        import redis.asyncio as aioredis  # lazy import

        self._redis = aioredis.from_url(redis_url, decode_responses=True)
        self._exec_ttl = exec_ttl_seconds

    # ── Definitions ──────────────────────────────────────────────────────────

    async def put_definition(self, wf: WorkflowDefinition) -> None:
        key = f"{self._WF_PREFIX}{wf.id}"
        ts = time.time()
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.set(key, json.dumps(wf.to_dict()))
            pipe.zadd(self._WF_INDEX, {wf.id: ts}, nx=True)  # nx: don't overwrite score
            await pipe.execute()

    async def get_definition(self, wf_id: str) -> WorkflowDefinition | None:
        raw = await self._redis.get(f"{self._WF_PREFIX}{wf_id}")
        if raw is None:
            return None
        return WorkflowDefinition.from_dict(json.loads(raw))

    async def list_definitions(self, limit: int = 20, offset: int = 0) -> list[WorkflowDefinition]:
        ids: list[str] = await self._redis.zrevrange(self._WF_INDEX, offset, offset + limit - 1)
        if not ids:
            return []
        keys = [f"{self._WF_PREFIX}{i}" for i in ids]
        raws = await self._redis.mget(*keys)
        return [WorkflowDefinition.from_dict(json.loads(r)) for r in raws if r is not None]

    async def count_definitions(self) -> int:
        return await self._redis.zcard(self._WF_INDEX)

    async def delete_definition(self, wf_id: str) -> bool:
        key = f"{self._WF_PREFIX}{wf_id}"
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.delete(key)
            pipe.zrem(self._WF_INDEX, wf_id)
            results = await pipe.execute()
        deleted: int = results[0]
        return deleted > 0

    # ── Executions ───────────────────────────────────────────────────────────

    async def put_execution(self, ex: WorkflowExecution) -> None:
        key = f"{self._EX_PREFIX}{ex.execution_id}"
        index_key = f"{self._EX_INDEX_PREFIX}{ex.workflow_id}"
        ts = time.time()
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.set(key, json.dumps(ex.to_dict()), ex=self._exec_ttl)
            pipe.zadd(index_key, {ex.execution_id: ts}, nx=True)
            pipe.expire(index_key, self._exec_ttl)
            await pipe.execute()

    async def get_execution(self, exec_id: str) -> WorkflowExecution | None:
        raw = await self._redis.get(f"{self._EX_PREFIX}{exec_id}")
        if raw is None:
            return None
        return WorkflowExecution.from_dict(json.loads(raw))

    async def list_executions(
        self, wf_id: str, limit: int = 20, offset: int = 0
    ) -> list[WorkflowExecution]:
        index_key = f"{self._EX_INDEX_PREFIX}{wf_id}"
        ids: list[str] = await self._redis.zrevrange(index_key, offset, offset + limit - 1)
        if not ids:
            return []
        keys = [f"{self._EX_PREFIX}{i}" for i in ids]
        raws = await self._redis.mget(*keys)
        return [WorkflowExecution.from_dict(json.loads(r)) for r in raws if r is not None]

    async def count_executions(self, wf_id: str) -> int:
        return await self._redis.zcard(f"{self._EX_INDEX_PREFIX}{wf_id}")

    async def close(self) -> None:
        await self._redis.close()
