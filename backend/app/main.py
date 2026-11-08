import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import Depends, FastAPI, WebSocket
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.database import get_db
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.core.config import settings
from app.core.logging_config import setup_logging
from app.core.security import LoopbackGuardMiddleware
from app.models.database import init_db
from app.migration import safe_migrate_db, safe_create_indexes
from app.api.router import api_router

logger = logging.getLogger(__name__)
from app.websocket.stream import stream_endpoint, view_endpoint
from app.websocket.control import control_endpoint
from app.websocket.video import video_endpoint
from app.websocket.devices import devices_endpoint
from app.websocket.execution_stream import execution_view_endpoint
from app.websocket.vision_stream import vision_view_endpoint
from app.websocket.workflow_stream import workflow_view_endpoint
from app.websocket.campaign_stream import campaign_view_endpoint
from app.websocket.orchestrator_stream import orchestrator_view_endpoint
from app.websocket.agent_stream import agent_view_endpoint

from app.core import runtime_paths, data_migration

FRONTEND_DIST = runtime_paths.frontend_dist()


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio
    from app.campaign.dispatcher import run_loop as campaign_run_loop
    from app.version import VERSION

    setup_logging(settings.log_level)
    logger.info("MirrorHub %s starting up", VERSION)

    if not settings.openai_api_key:
        logger.warning(
            "OPENAI_API_KEY not set in backend/.env — "
            "AI features (content generation, vision) will be unavailable"
        )

    startup_report = data_migration.startup()
    logger.info("Data dir: %s (%s)", runtime_paths.data_dir(), startup_report.get("migration", {}).get("status"))
    await safe_migrate_db()
    await safe_create_indexes()
    await init_db()
    _dispatcher_task = asyncio.create_task(campaign_run_loop())
    logger.info("Campaign dispatcher started")

    from app.orchestrator.monitor import run_monitor, stop_monitor
    _monitor_task = asyncio.create_task(run_monitor())
    logger.info("Orchestrator monitor started")

    from app.agents.manager import run_loop as agent_run_loop, stop_agents
    _agent_task = asyncio.create_task(agent_run_loop())
    logger.info("AI Agent manager started")

    async def _gc_loop() -> None:
        # asyncio subprocess/websocket objects form reference cycles; Python's lazy gen-2 collection let RSS climb
        # ~5 MB/min (sawtooth up to ~270 MB in a 25 min real soak). A cheap periodic full collection keeps it flat.
        import gc
        while True:
            await asyncio.sleep(30)
            gc.collect()

    _gc_task = asyncio.create_task(_gc_loop())

    from app.devices.lifecycle import get_monitor
    _device_monitor = get_monitor()
    _device_monitor.start()
    logger.info("Device monitor started")

    try:
        yield
    finally:
        from app.campaign.dispatcher import stop as campaign_stop
        campaign_stop()
        _dispatcher_task.cancel()
        stop_monitor()
        _monitor_task.cancel()
        stop_agents()
        _agent_task.cancel()
        _gc_task.cancel()
        await _device_monitor.stop()
        from app.automation.core import get_engine
        await get_engine().shutdown()
        from app.services.scrcpy_stream import stream_manager
        await stream_manager.stop_all()
        logger.info("MirrorHub shutdown complete")


app = FastAPI(title=settings.app_name, lifespan=lifespan)

# Only the local UI may talk to this API (ADR-004). "*" in CORS_ORIGINS is no longer
# honoured: the API drives physical phones without authentication.
_extra_origins = {
    o.strip() for o in settings.cors_origins.split(",") if o.strip() and o.strip() != "*"
}
if settings.cors_origins.strip() == "*":
    logger.warning("CORS_ORIGINS=* ignored; only loopback origins are allowed")
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(127\.0\.0\.1|localhost|\[::1\])(:\d{1,5})?$",
    allow_origins=sorted(_extra_origins),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(LoopbackGuardMiddleware, extra_origins=_extra_origins)

app.include_router(api_router)


# ── WebSocket routes ──────────────────────────────────────────────────────────

@app.websocket("/ws/stream/{device_id}")
async def ws_stream(device_id: str, ws: WebSocket):
    """Android agent → pushes screen frames to backend."""
    await stream_endpoint(device_id, ws)


@app.websocket("/ws/view/{device_id}")
async def ws_view(device_id: str, ws: WebSocket, db: AsyncSession = Depends(get_db)):
    """Browser → receives screen frames from backend."""
    await view_endpoint(device_id, ws, db)


@app.websocket("/ws/control/{device_id}")
async def ws_control(device_id: str, ws: WebSocket, db: AsyncSession = Depends(get_db)):
    """Browser → sends touch/keyboard commands → ADB or Android agent."""
    await control_endpoint(device_id, ws, db)


@app.websocket("/ws/devices")
async def ws_devices(ws: WebSocket):
    """Device lifecycle events (hot-plug, authorization, reconnect, adb outage)."""
    await devices_endpoint(ws)


@app.websocket("/ws/video/{device_id}")
async def ws_video(device_id: str, ws: WebSocket, db: AsyncSession = Depends(get_db)):
    """Embedded scrcpy H.264 NAL stream → browser WebCodecs decoder (?profile=thumb|normal|focus)."""
    await video_endpoint(device_id, ws, db)


@app.websocket("/ws/execution/{device_id}")
async def ws_execution(device_id: str, ws: WebSocket):
    """Execution monitor → receives live execution state updates."""
    await execution_view_endpoint(device_id, ws)


@app.websocket("/ws/vision/{device_id}")
async def ws_vision(device_id: str, ws: WebSocket):
    """Vision debugger → receives live ScreenAnalysis updates."""
    await vision_view_endpoint(device_id, ws)


@app.websocket("/ws/workflow/{channel_id}")
async def ws_workflow(channel_id: str, ws: WebSocket):
    """Workflow player/recorder → receives progress and recorder events."""
    await workflow_view_endpoint(channel_id, ws)


@app.websocket("/ws/campaign/{channel_id}")
async def ws_campaign(channel_id: str, ws: WebSocket):
    """Campaign/queue monitor → receives live queue and campaign updates."""
    await campaign_view_endpoint(channel_id, ws)


@app.websocket("/ws/orchestrator/{channel_id}")
async def ws_orchestrator(channel_id: str, ws: WebSocket):
    """Orchestrator fleet monitor → receives device status and failover events."""
    await orchestrator_view_endpoint(channel_id, ws)


@app.websocket("/ws/agents")
async def ws_agents(ws: WebSocket):
    """AI Agent layer → broadcasts all agent events (decisions, tasks, recovery, optimization)."""
    await agent_view_endpoint(ws)


@app.get("/health")
async def health():
    return {"status": "ok", "app": settings.app_name}


# ── Serve built React frontend (App Mode) ─────────────────────────────────────
# Only mount if dist/ exists — dev mode uses Vite instead
UPLOADS_DIR = runtime_paths.uploads_dir()
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend(full_path: str = ""):
        return FileResponse(str(FRONTEND_DIST / "index.html"))
