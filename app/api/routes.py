from fastapi import APIRouter

from app.api.endpoints.agents import agents_router
from app.api.endpoints.evaluation import evaluation_router
from app.api.endpoints.health import health_router
from app.api.endpoints.messages import messages_router
from app.api.endpoints.metrics import metrics_router
from app.api.endpoints.tools import tools_router
from app.api.endpoints.trace import trace_router
from app.api.endpoints.workflows import workflows_router

router = APIRouter()

router.include_router(messages_router)
router.include_router(evaluation_router)
router.include_router(trace_router)
router.include_router(metrics_router)
router.include_router(health_router)
router.include_router(tools_router)
router.include_router(workflows_router)
router.include_router(agents_router)
