from fastapi import APIRouter
from app.api.devices import router as devices_router
from app.api.mirror import router as mirror_router
from app.api.automation import router as automation_router
from app.api.products import router as products_router
from app.content.routes import router as content_router
from app.execution.routes import router as execution_router
from app.vision.routes import router as vision_router
from app.apps.youtube_create.routes import router as ytc_plugin_router
from app.apps.tiktok.routes import router as tiktok_plugin_router
from app.workflows.routes import router as workflow_router
from app.campaign.routes import router as campaign_router
from app.api.system import router as system_router
from app.orchestrator.routes import router as orchestrator_router
from app.agents.routes import router as agents_router
from app.api.quicklaunch import router as quicklaunch_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(devices_router)
api_router.include_router(mirror_router)
api_router.include_router(automation_router)
api_router.include_router(products_router)
api_router.include_router(content_router)
api_router.include_router(execution_router)
api_router.include_router(vision_router)
api_router.include_router(ytc_plugin_router)
api_router.include_router(tiktok_plugin_router)
api_router.include_router(workflow_router)
api_router.include_router(campaign_router)
api_router.include_router(system_router)
api_router.include_router(orchestrator_router)
api_router.include_router(agents_router)
api_router.include_router(quicklaunch_router)
