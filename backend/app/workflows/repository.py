"""Database CRUD helpers for the Workflow module."""
import json
from datetime import datetime, timezone

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Workflow, WorkflowVersion, WorkflowStep, WorkflowExecution


# ── Workflow ──────────────────────────────────────────────────────────────────

async def create_workflow(db: AsyncSession, name: str, description: str = "",
                          application: str = "generic",
                          variables: list[str] | None = None) -> Workflow:
    wf = Workflow(
        name=name,
        description=description,
        application=application,
        variables_json=json.dumps(variables or []),
    )
    db.add(wf)
    await db.commit()
    await db.refresh(wf)
    return wf


async def get_workflow(db: AsyncSession, workflow_id: int) -> Workflow | None:
    return await db.get(Workflow, workflow_id)


async def list_workflows(db: AsyncSession) -> list[Workflow]:
    result = await db.execute(select(Workflow).order_by(Workflow.updated_at.desc()))
    return list(result.scalars().all())


async def update_workflow(db: AsyncSession, workflow_id: int, **kwargs) -> Workflow | None:
    wf = await db.get(Workflow, workflow_id)
    if not wf:
        return None
    for k, v in kwargs.items():
        if k == "variables":
            wf.variables_json = json.dumps(v)
        elif hasattr(wf, k):
            setattr(wf, k, v)
    wf.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(wf)
    return wf


async def delete_workflow(db: AsyncSession, workflow_id: int) -> bool:
    wf = await db.get(Workflow, workflow_id)
    if not wf:
        return False
    await db.execute(delete(WorkflowStep).where(WorkflowStep.workflow_id == workflow_id))
    await db.execute(delete(WorkflowVersion).where(WorkflowVersion.workflow_id == workflow_id))
    await db.delete(wf)
    await db.commit()
    return True


# ── Steps ─────────────────────────────────────────────────────────────────────

async def get_steps(db: AsyncSession, workflow_id: int) -> list[WorkflowStep]:
    result = await db.execute(
        select(WorkflowStep)
        .where(WorkflowStep.workflow_id == workflow_id)
        .order_by(WorkflowStep.order)
    )
    return list(result.scalars().all())


async def add_step(db: AsyncSession, workflow_id: int,
                   step_type: str, label: str = "", parameters: dict | None = None,
                   conditions: dict | None = None, retry_max: int = 2,
                   timeout: int = 30, enabled: bool = True,
                   screen_name: str | None = None,
                   screenshot_path: str | None = None,
                   order: int | None = None) -> WorkflowStep:
    if order is None:
        existing = await get_steps(db, workflow_id)
        order = len(existing)
    step = WorkflowStep(
        workflow_id=workflow_id,
        order=order,
        step_type=step_type,
        label=label or step_type,
        parameters_json=json.dumps(parameters or {}),
        conditions_json=json.dumps(conditions or {}),
        retry_max=retry_max,
        timeout=timeout,
        enabled=enabled,
        screen_name=screen_name,
        screenshot_path=screenshot_path,
    )
    db.add(step)
    await db.commit()
    await db.refresh(step)
    return step


async def update_step(db: AsyncSession, step_id: int, **kwargs) -> WorkflowStep | None:
    step = await db.get(WorkflowStep, step_id)
    if not step:
        return None
    for k, v in kwargs.items():
        if k == "parameters":
            step.parameters_json = json.dumps(v)
        elif k == "conditions":
            step.conditions_json = json.dumps(v)
        elif hasattr(step, k):
            setattr(step, k, v)
    await db.commit()
    await db.refresh(step)
    return step


async def delete_step(db: AsyncSession, step_id: int) -> bool:
    step = await db.get(WorkflowStep, step_id)
    if not step:
        return False
    await db.delete(step)
    await db.commit()
    return True


async def reorder_steps(db: AsyncSession, workflow_id: int, step_ids: list[int]) -> list[WorkflowStep]:
    """Re-assign order= values based on supplied step_ids list."""
    for i, sid in enumerate(step_ids):
        step = await db.get(WorkflowStep, sid)
        if step and step.workflow_id == workflow_id:
            step.order = i
    await db.commit()
    return await get_steps(db, workflow_id)


# ── Versions ──────────────────────────────────────────────────────────────────

async def save_version(db: AsyncSession, workflow_id: int,
                       notes: str | None = None) -> WorkflowVersion:
    wf = await db.get(Workflow, workflow_id)
    if not wf:
        raise ValueError(f"Workflow {workflow_id} not found")
    steps = await get_steps(db, workflow_id)
    next_ver = wf.current_version + 1
    ver = WorkflowVersion(
        workflow_id=workflow_id,
        version=next_ver,
        steps_json=json.dumps([s.to_dict() for s in steps]),
        variables_json=wf.variables_json,
        notes=notes,
    )
    db.add(ver)
    wf.current_version = next_ver
    wf.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(ver)
    return ver


async def list_versions(db: AsyncSession, workflow_id: int) -> list[WorkflowVersion]:
    result = await db.execute(
        select(WorkflowVersion)
        .where(WorkflowVersion.workflow_id == workflow_id)
        .order_by(WorkflowVersion.version.desc())
    )
    return list(result.scalars().all())


async def rollback_to_version(db: AsyncSession, workflow_id: int, version: int) -> bool:
    """Replace current workflow_steps with the snapshot from a version."""
    result = await db.execute(
        select(WorkflowVersion)
        .where(WorkflowVersion.workflow_id == workflow_id,
               WorkflowVersion.version == version)
    )
    ver = result.scalar_one_or_none()
    if not ver:
        return False
    # Delete current steps
    await db.execute(delete(WorkflowStep).where(WorkflowStep.workflow_id == workflow_id))
    # Restore from snapshot
    snapshot = json.loads(ver.steps_json or "[]")
    for s in snapshot:
        db.add(WorkflowStep(
            workflow_id=workflow_id,
            order=s.get("order", 0),
            step_type=s.get("step_type", ""),
            label=s.get("label", ""),
            parameters_json=json.dumps(s.get("parameters", {})),
            conditions_json=json.dumps(s.get("conditions", {})),
            retry_max=s.get("retry_max", 2),
            timeout=s.get("timeout", 30),
            enabled=s.get("enabled", True),
            screen_name=s.get("screen_name"),
            screenshot_path=s.get("screenshot_path"),
        ))
    await db.commit()
    return True


# ── Executions ────────────────────────────────────────────────────────────────

async def create_execution(db: AsyncSession, workflow_id: int, workflow_version: int,
                           device_id: str, adb_address: str,
                           variables: dict | None = None) -> WorkflowExecution:
    exc = WorkflowExecution(
        workflow_id=workflow_id,
        workflow_version=workflow_version,
        device_id=device_id,
        adb_address=adb_address,
        variables_json=json.dumps(variables or {}),
    )
    db.add(exc)
    await db.commit()
    await db.refresh(exc)
    return exc


async def list_executions(db: AsyncSession, limit: int = 50) -> list[WorkflowExecution]:
    result = await db.execute(
        select(WorkflowExecution).order_by(WorkflowExecution.started_at.desc()).limit(limit)
    )
    return list(result.scalars().all())


async def get_execution(db: AsyncSession, execution_id: int) -> WorkflowExecution | None:
    return await db.get(WorkflowExecution, execution_id)
