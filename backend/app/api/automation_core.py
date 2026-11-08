"""
Automation core API.

POST /auto/validate           {steps}                       → normalized steps or 400 with the exact bad step
POST /auto/runs               {name, device_ids, steps}     → starts a run (409 if a device is offline/busy)
GET  /auto/runs                                              → recent runs
GET  /auto/runs/{id}                                         → full status + per-device logs
POST /auto/runs/{id}/cancel
GET  /auto/step-types
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.automation.core import STEP_FIELDS, STEP_LABELS, StepValidationError, get_engine, validate_steps
from app.devices import registry
from app.models.database import get_db

router = APIRouter(prefix="/auto", tags=["automation-core"])


class ValidateRequest(BaseModel):
    steps: list[dict]


class RunRequest(BaseModel):
    name: str = Field("Automasi", max_length=80)
    device_ids: list[str] = Field(min_length=1, max_length=100)
    steps: list[dict]


@router.get("/step-types")
async def step_types():
    return [{"type": t, "label": STEP_LABELS[t], "fields": list(f)} for t, f in STEP_FIELDS.items()]


@router.post("/validate")
async def validate(req: ValidateRequest):
    try:
        return {"ok": True, "steps": validate_steps(req.steps)}
    except StepValidationError as exc:
        raise HTTPException(400, str(exc))


@router.post("/runs")
async def start_run(req: RunRequest, db: AsyncSession = Depends(get_db)):
    try:
        steps = validate_steps(req.steps)
    except StepValidationError as exc:
        raise HTTPException(400, str(exc))
    devices: list[tuple[str, str, str]] = []
    problems: list[str] = []
    for did in dict.fromkeys(req.device_ids):
        d = await registry.get_device(db, did)
        if d is None:
            problems.append(f"{did}: tidak dijumpai")
        elif not d.is_online or not d.adb_address:
            problems.append(f"{d.device_name}: offline")
        else:
            devices.append((d.device_id, d.adb_address, d.device_name))
    if problems:
        raise HTTPException(409, "Peranti tidak sedia: " + "; ".join(problems))
    try:
        run = get_engine().start(req.name, steps, devices)
    except StepValidationError as exc:
        raise HTTPException(409, str(exc))
    return run.to_dict()


@router.get("/runs")
async def list_runs():
    return [r.to_dict() for r in get_engine().list()]


@router.get("/runs/{run_id}")
async def get_run(run_id: str):
    run = get_engine().get(run_id)
    if run is None:
        raise HTTPException(404, "Run tidak dijumpai.")
    return run.to_dict(with_logs=True)


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str):
    eng = get_engine()
    if eng.get(run_id) is None:
        raise HTTPException(404, "Run tidak dijumpai.")
    return {"ok": eng.cancel(run_id)}
