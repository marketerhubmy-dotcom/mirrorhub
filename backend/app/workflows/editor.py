"""
Workflow editor helpers — pure business logic, no HTTP layer.

Provides step manipulation operations used by the routes layer.
"""
import json
from sqlalchemy.ext.asyncio import AsyncSession
from .models import WorkflowStep
from .repository import get_steps, update_step, add_step, delete_step


async def duplicate_step(db: AsyncSession, step_id: int) -> WorkflowStep | None:
    """Clone a step, appending it immediately after the original."""
    original = await db.get(WorkflowStep, step_id)
    if not original:
        return None
    steps = await get_steps(db, original.workflow_id)

    # Shift orders after original
    new_order = original.order + 1
    for s in steps:
        if s.order >= new_order and s.id != step_id:
            s.order += 1
    await db.flush()

    return await add_step(
        db,
        workflow_id=original.workflow_id,
        step_type=original.step_type,
        label=f"{original.label} (copy)",
        parameters=json.loads(original.parameters_json or "{}"),
        conditions=json.loads(original.conditions_json or "{}"),
        retry_max=original.retry_max,
        timeout=original.timeout,
        enabled=original.enabled,
        screen_name=original.screen_name,
        order=new_order,
    )


async def move_step_up(db: AsyncSession, step_id: int) -> bool:
    step = await db.get(WorkflowStep, step_id)
    if not step or step.order == 0:
        return False
    steps = await get_steps(db, step.workflow_id)
    prev = next((s for s in steps if s.order == step.order - 1), None)
    if not prev:
        return False
    prev.order, step.order = step.order, prev.order
    await db.commit()
    return True


async def move_step_down(db: AsyncSession, step_id: int) -> bool:
    step = await db.get(WorkflowStep, step_id)
    if not step:
        return False
    steps = await get_steps(db, step.workflow_id)
    nxt = next((s for s in steps if s.order == step.order + 1), None)
    if not nxt:
        return False
    nxt.order, step.order = step.order, nxt.order
    await db.commit()
    return True
