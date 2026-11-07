"""
Content Agent.

Processes GENERATE_CONTENT tasks by calling the existing Content Pipeline.
Generates: brief (hook/story/cta) + video_prompt + caption + hashtags.

Delegates ALL generation to app.content.service — no duplicate OpenAI calls.
"""
from __future__ import annotations

import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.content.service import generate_content
from app.content.schemas import GenerateRequest
from app.content.repository import get_job as get_content_job
from . import repository as repo
from .models import AgentTask, TASK_RUNNING, TASK_COMPLETED, TASK_FAILED
from . import memory as mem

logger = logging.getLogger(__name__)


class ContentAgent:
    """Runs content generation tasks created by PlannerAgent."""

    async def run_task(self, db: AsyncSession, task: AgentTask) -> None:
        """Process one GENERATE_CONTENT task end-to-end."""
        await repo.update_task(db, task, TASK_RUNNING)
        input_data = json.loads(task.input_json or "{}")
        content_job_id = input_data.get("content_job_id")
        product = input_data.get("product", "")
        platform = input_data.get("platform", "tiktok")

        if not content_job_id:
            await repo.update_task(db, task, TASK_FAILED, error="Missing content_job_id")
            return

        content_job = await get_content_job(db, content_job_id)
        if not content_job:
            await repo.update_task(db, task, TASK_FAILED, error=f"ContentJob {content_job_id} not found")
            return

        try:
            updated = await generate_content(
                db,
                content_job,
                GenerateRequest(brief=True, video_prompt=True, caption=True, hashtags=True),
            )
            output = {
                "content_job_id": updated.id,
                "status": updated.status,
                "hook": updated.hook[:80] if updated.hook else "",
                "video_prompt_len": len(updated.video_prompt),
                "caption_len": len(updated.caption),
            }
            await repo.update_task(db, task, TASK_COMPLETED, output=output)

            # Store successful prompt in memory
            if updated.video_prompt:
                await mem.remember_successful_prompt(
                    db, product, platform, updated.video_prompt[:200]
                )

            logger.info(
                "ContentAgent: task %d completed — ContentJob %d → %s",
                task.id, updated.id, updated.status,
            )
        except Exception as exc:
            logger.exception("ContentAgent: task %d failed: %s", task.id, exc)
            await repo.update_task(db, task, TASK_FAILED, error=str(exc))


content_agent = ContentAgent()
