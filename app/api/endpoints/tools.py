from fastapi import APIRouter, Request

from app.registry.tool_registry import ToolRegistry

tools_router = APIRouter(prefix="/tools", tags=["tools"])


@tools_router.get("")
def list_tools(request: Request) -> dict[str, list[str]]:
    registry: ToolRegistry = request.app.state.tool_registry
    return {"tools": sorted(registry.names())}
