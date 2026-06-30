from fastapi import APIRouter, Request

from app.runtime.runtime import AgentOpsRuntime
from app.schemas.messages import BatchRequest, BatchResponse, MessageRequest, MessageResponse

messages_router = APIRouter(tags=["messages"])


@messages_router.post("/messages", response_model=MessageResponse)
async def post_message(req: MessageRequest, request: Request) -> MessageResponse:
    runtime: AgentOpsRuntime = request.app.state.runtime
    return await runtime.handle_message(req)


@messages_router.post("/messages/batch", response_model=BatchResponse)
async def post_batch(req: BatchRequest, request: Request) -> BatchResponse:
    runtime: AgentOpsRuntime = request.app.state.runtime
    return await runtime.handle_batch(req)
