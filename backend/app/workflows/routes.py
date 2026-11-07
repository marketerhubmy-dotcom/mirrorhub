"""
Workflow API routes.

Prefixed at /api/v1/workflows by the router.
"""
import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.devices.registry import get_device
from app.models.database import get_db
from .models import WorkflowStep
from .schemas import (
    WorkflowCreate, WorkflowUpdate, StepCreate, StepUpdate, StepReorder,
    VersionCreate, PlayRequest, RecorderStartRequest, RecorderStepRequest,
    RecorderStopRequest, ImportRequest,
)
from . import repository as repo
from . import recorder as rec
from .editor import duplicate_step, move_step_up, move_step_down
from .serializer import export_workflow, import_workflow
from .validator import validate_steps
from .player import play_workflow, get_runner

router = APIRouter(prefix="/workflows", tags=["workflows"])


# ── Utility ───────────────────────────────────────────────────────────────────

async def _wf_or_404(db: AsyncSession, wid: int):
    wf = await repo.get_workflow(db, wid)
    if not wf:
        raise HTTPException(404, "Workflow not found")
    return wf


# ── Workflow CRUD ─────────────────────────────────────────────────────────────

@router.get("")
async def list_workflows(db: AsyncSession = Depends(get_db)):
    workflows = await repo.list_workflows(db)
    result = []
    for wf in workflows:
        d = wf.to_dict()
        steps = await repo.get_steps(db, wf.id)
        d["step_count"] = len(steps)
        result.append(d)
    return result


@router.post("")
async def create_workflow(req: WorkflowCreate, db: AsyncSession = Depends(get_db)):
    wf = await repo.create_workflow(
        db, name=req.name, description=req.description,
        application=req.application, variables=req.variables,
    )
    return wf.to_dict()


@router.get("/{workflow_id}")
async def get_workflow(workflow_id: int, db: AsyncSession = Depends(get_db)):
    wf = await _wf_or_404(db, workflow_id)
    d = wf.to_dict()
    d["steps"] = [s.to_dict() for s in await repo.get_steps(db, workflow_id)]
    return d


@router.put("/{workflow_id}")
async def update_workflow(workflow_id: int, req: WorkflowUpdate,
                          db: AsyncSession = Depends(get_db)):
    wf = await _wf_or_404(db, workflow_id)
    kwargs = {k: v for k, v in req.model_dump().items() if v is not None}
    wf = await repo.update_workflow(db, workflow_id, **kwargs)
    return wf.to_dict()


@router.delete("/{workflow_id}")
async def delete_workflow(workflow_id: int, db: AsyncSession = Depends(get_db)):
    await _wf_or_404(db, workflow_id)
    await repo.delete_workflow(db, workflow_id)
    return {"deleted": workflow_id}


# ── Steps ─────────────────────────────────────────────────────────────────────

@router.get("/{workflow_id}/steps")
async def list_steps(workflow_id: int, db: AsyncSession = Depends(get_db)):
    await _wf_or_404(db, workflow_id)
    return [s.to_dict() for s in await repo.get_steps(db, workflow_id)]


@router.post("/{workflow_id}/steps")
async def add_step(workflow_id: int, req: StepCreate, db: AsyncSession = Depends(get_db)):
    await _wf_or_404(db, workflow_id)
    step = await repo.add_step(
        db, workflow_id=workflow_id,
        step_type=req.step_type, label=req.label,
        parameters=req.parameters, conditions=req.conditions,
        retry_max=req.retry_max, timeout=req.timeout,
        enabled=req.enabled, screen_name=req.screen_name,
        order=req.order,
    )
    return step.to_dict()


@router.put("/{workflow_id}/steps/{step_id}")
async def update_step(workflow_id: int, step_id: int, req: StepUpdate,
                      db: AsyncSession = Depends(get_db)):
    await _wf_or_404(db, workflow_id)
    kwargs = {k: v for k, v in req.model_dump().items() if v is not None}
    step = await repo.update_step(db, step_id, **kwargs)
    if not step:
        raise HTTPException(404, "Step not found")
    return step.to_dict()


@router.delete("/{workflow_id}/steps/{step_id}")
async def delete_step(workflow_id: int, step_id: int, db: AsyncSession = Depends(get_db)):
    await _wf_or_404(db, workflow_id)
    deleted = await repo.delete_step(db, step_id)
    if not deleted:
        raise HTTPException(404, "Step not found")
    return {"deleted": step_id}


@router.post("/{workflow_id}/steps/{step_id}/duplicate")
async def dup_step(workflow_id: int, step_id: int, db: AsyncSession = Depends(get_db)):
    await _wf_or_404(db, workflow_id)
    new_step = await duplicate_step(db, step_id)
    if not new_step:
        raise HTTPException(404, "Step not found")
    return new_step.to_dict()


@router.post("/{workflow_id}/steps/{step_id}/move_up")
async def step_move_up(workflow_id: int, step_id: int, db: AsyncSession = Depends(get_db)):
    await move_step_up(db, step_id)
    return [s.to_dict() for s in await repo.get_steps(db, workflow_id)]


@router.post("/{workflow_id}/steps/{step_id}/move_down")
async def step_move_down(workflow_id: int, step_id: int, db: AsyncSession = Depends(get_db)):
    await move_step_down(db, step_id)
    return [s.to_dict() for s in await repo.get_steps(db, workflow_id)]


@router.post("/{workflow_id}/steps/reorder")
async def reorder_steps(workflow_id: int, req: StepReorder, db: AsyncSession = Depends(get_db)):
    await _wf_or_404(db, workflow_id)
    steps = await repo.reorder_steps(db, workflow_id, req.step_ids)
    return [s.to_dict() for s in steps]


# ── Validation ────────────────────────────────────────────────────────────────

@router.post("/{workflow_id}/validate")
async def validate_workflow(workflow_id: int, db: AsyncSession = Depends(get_db)):
    wf = await _wf_or_404(db, workflow_id)
    steps = await repo.get_steps(db, workflow_id)
    variables = json.loads(wf.variables_json or "[]")
    result = validate_steps(steps, variables)
    return result.to_dict()


# ── Versioning ────────────────────────────────────────────────────────────────

@router.get("/{workflow_id}/versions")
async def list_versions(workflow_id: int, db: AsyncSession = Depends(get_db)):
    await _wf_or_404(db, workflow_id)
    versions = await repo.list_versions(db, workflow_id)
    return [v.to_dict() for v in versions]


@router.post("/{workflow_id}/versions")
async def save_version(workflow_id: int, req: VersionCreate, db: AsyncSession = Depends(get_db)):
    await _wf_or_404(db, workflow_id)
    ver = await repo.save_version(db, workflow_id, notes=req.notes)
    return ver.to_dict()


@router.post("/{workflow_id}/versions/{version}/rollback")
async def rollback(workflow_id: int, version: int, db: AsyncSession = Depends(get_db)):
    await _wf_or_404(db, workflow_id)
    ok = await repo.rollback_to_version(db, workflow_id, version)
    if not ok:
        raise HTTPException(404, "Version not found")
    steps = await repo.get_steps(db, workflow_id)
    return {"rolled_back_to": version, "step_count": len(steps)}


# ── Import / Export ───────────────────────────────────────────────────────────

@router.get("/{workflow_id}/export")
async def export(workflow_id: int, db: AsyncSession = Depends(get_db)):
    wf = await _wf_or_404(db, workflow_id)
    steps = await repo.get_steps(db, workflow_id)
    data = export_workflow(wf, steps)
    return JSONResponse(content=data, headers={
        "Content-Disposition": f'attachment; filename="workflow_{workflow_id}.json"',
    })


@router.post("/import")
async def import_wf(req: ImportRequest, db: AsyncSession = Depends(get_db)):
    try:
        meta, steps_data = import_workflow(req.workflow_json)
    except ValueError as e:
        raise HTTPException(422, str(e))

    wf = await repo.create_workflow(
        db, name=meta["name"], description=meta["description"],
        application=meta["application"], variables=meta["variables"],
    )
    for s in steps_data:
        await repo.add_step(db, workflow_id=wf.id, **s)

    d = wf.to_dict()
    d["step_count"] = len(steps_data)
    return d


# ── Player ────────────────────────────────────────────────────────────────────

@router.post("/{workflow_id}/play")
async def play(workflow_id: int, req: PlayRequest, db: AsyncSession = Depends(get_db)):
    wf = await _wf_or_404(db, workflow_id)
    device = await get_device(db, req.device_id)
    if not device:
        raise HTTPException(404, "Device not found")
    if not device.adb_address:
        raise HTTPException(400, "Device has no ADB address")

    steps = await repo.get_steps(db, workflow_id)
    if not steps:
        raise HTTPException(400, "Workflow has no steps")

    execution = await play_workflow(
        workflow_id=workflow_id,
        device_id=req.device_id,
        adb_address=device.adb_address,
        steps=steps,
        current_version=wf.current_version,
        variables=req.variables,
        simulate=req.simulate,
    )
    return {
        "execution_id": execution.id,
        "workflow_id": workflow_id,
        "status": "started",
        "simulate": req.simulate,
        "total_steps": len([s for s in steps if s.enabled]),
    }


@router.get("/executions/list")
async def list_executions(db: AsyncSession = Depends(get_db)):
    execs = await repo.list_executions(db)
    return [e.to_dict() for e in execs]


@router.get("/executions/{execution_id}")
async def get_execution(execution_id: int, db: AsyncSession = Depends(get_db)):
    exc = await repo.get_execution(db, execution_id)
    if not exc:
        raise HTTPException(404, "Execution not found")
    return exc.to_dict()


@router.post("/executions/{execution_id}/cancel")
async def cancel_execution(execution_id: int):
    runner = get_runner(execution_id)
    if not runner:
        raise HTTPException(404, "Execution not active")
    runner.cancel()
    return {"cancelled": execution_id}


# ── Recorder ─────────────────────────────────────────────────────────────────

@router.post("/recorder/start")
async def recorder_start(req: RecorderStartRequest, db: AsyncSession = Depends(get_db)):
    device = await get_device(db, req.device_id)
    if not device:
        raise HTTPException(404, "Device not found")
    if not device.adb_address:
        raise HTTPException(400, "Device has no ADB address")
    session = rec.start_session(req.device_id, device.adb_address, req.name)
    # Broadcast to WS
    from app.websocket.manager import manager
    import json
    await manager.broadcast_workflow(
        session.session_id,
        json.dumps({"type": "recording_started", "session": session.to_dict()}),
    )
    return session.to_dict()


@router.get("/recorder/sessions")
async def recorder_sessions():
    return rec.list_sessions()


@router.get("/recorder/{session_id}")
async def recorder_get(session_id: str):
    session = rec.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return session.to_dict()


@router.post("/recorder/{session_id}/step")
async def recorder_add_step(session_id: str, req: RecorderStepRequest):
    session = rec.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    screen_name = None
    screenshot_path = None
    if req.capture_screen:
        screen_name, screenshot_path = await rec.capture_step_context(
            session.adb_address, session.device_id
        )

    step = session.add_step(
        step_type=req.step_type,
        label=req.label,
        parameters=req.parameters,
        conditions=req.conditions,
        screen_name=screen_name,
        screenshot_path=screenshot_path,
    )

    from app.websocket.manager import manager
    import json
    await manager.broadcast_workflow(
        session_id,
        json.dumps({"type": "step_added", "step": step}),
    )
    return {"step": step, "total_steps": len(session.steps)}


@router.delete("/recorder/{session_id}/steps/{index}")
async def recorder_remove_step(session_id: str, index: int):
    session = rec.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    removed = session.remove_step(index)
    if not removed:
        raise HTTPException(400, "Invalid step index")
    return {"removed": index, "total_steps": len(session.steps)}


@router.post("/recorder/{session_id}/stop")
async def recorder_stop(session_id: str, req: RecorderStopRequest,
                        db: AsyncSession = Depends(get_db)):
    session = rec.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    result: dict = {"session_id": session_id, "saved": False}

    if req.save and session.steps:
        wf = await repo.create_workflow(
            db,
            name=req.name or session.name,
            description=req.description,
            application=req.application,
            variables=[],
        )
        for s in session.steps:
            await repo.add_step(
                db,
                workflow_id=wf.id,
                step_type=s["step_type"],
                label=s["label"],
                parameters=s["parameters"],
                conditions=s["conditions"],
                retry_max=s.get("retry_max", 2),
                timeout=s.get("timeout", 30),
                enabled=s.get("enabled", True),
                screen_name=s.get("screen_name"),
                screenshot_path=s.get("screenshot_path"),
                order=s["order"],
            )
        result["workflow"] = wf.to_dict()
        result["workflow"]["step_count"] = len(session.steps)
        result["saved"] = True

    rec.remove_session(session_id)

    from app.websocket.manager import manager
    import json as _json
    await manager.broadcast_workflow(
        session_id,
        _json.dumps({"type": "recording_stopped", "session_id": session_id}),
    )

    return result


# ── Step types catalog ────────────────────────────────────────────────────────

@router.get("/meta/step_types")
async def step_types():
    from .validator import STEP_SCHEMA
    return {
        "step_types": [
            {"type": k, "required_params": v}
            for k, v in STEP_SCHEMA.items()
        ]
    }
