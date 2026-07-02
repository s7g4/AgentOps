from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.runtime.trace_store import TraceStore

trace_router = APIRouter(prefix="/trace", tags=["trace"])


@trace_router.get("/{trace_id}")
async def get_trace(trace_id: str, request: Request) -> dict[str, object]:
    store: TraceStore = request.app.state.trace_store
    trace = await store.get(trace_id)

    if trace is None:
        raise HTTPException(status_code=404, detail=f"Trace '{trace_id}' not found")

    return trace.to_dict()


@trace_router.get("/")
async def list_traces(
    request: Request,
    limit: int = 50,
    offset: int = 0,
) -> JSONResponse:
    """List recent traces with pagination.

    Query params:
      limit  — max results (default 50, max 200)
      offset — skip N most-recent traces (for pagination)
    """
    store: TraceStore = request.app.state.trace_store
    limit = min(limit, 200)
    traces = await store.list_traces(limit=limit, offset=offset)
    total = await store.count()
    return JSONResponse(
        content={
            "total": total,
            "limit": limit,
            "offset": offset,
            "traces": [t.to_dict() for t in traces],
        }
    )
