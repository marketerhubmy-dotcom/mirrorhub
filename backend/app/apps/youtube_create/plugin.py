"""
YouTubeCreatePlugin — first concrete AppPlugin implementation.

Entry points:
    validate()  — check job dict before touching the device
    launch()    — open the app, confirm home screen via Vision Engine
    prepare()   — no-op; asset push is handled inside workflow steps
    execute()   — validate → build steps → start Execution Engine
                  (or log planned steps in simulation mode)
    finish()    — reserved for future cleanup

Simulation mode:
    Set job["simulate"] = True.  The plugin runs full validation + workflow
    build, then returns the planned steps WITHOUT calling the Execution Engine.
    Useful for testing workflows without a connected device.
"""
import asyncio
import subprocess

from app.apps.base import AppPlugin, PluginResult
from app.utils.adb_path import ADB
from .constants import PACKAGE_NAME, LAUNCH_TIMEOUT
from .state import ERRORS
from .validators import validate
from .workflow import build_workflow


class YouTubeCreatePlugin(AppPlugin):

    @property
    def app_id(self) -> str:
        return "youtube_create"

    # ── validate ──────────────────────────────────────────────────────────────

    async def validate(self, job: dict) -> PluginResult:
        return validate(job)

    # ── launch ────────────────────────────────────────────────────────────────

    async def launch(self, adb_address: str, device_id: str) -> PluginResult:
        """Open YouTube Create via ADB monkey launch, then wait for home screen."""
        proc = await asyncio.create_subprocess_exec(
            str(ADB), "-s", adb_address,
            "shell", "monkey", "-p", PACKAGE_NAME,
            "-c", "android.intent.category.LAUNCHER", "1",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        await proc.communicate()

        if device_id:
            from app.vision.analyzer import wait_until
            analysis = await wait_until(
                adb_address, device_id,
                button="New project",
                timeout=LAUNCH_TIMEOUT,
                poll_interval=2.0,
            )
            if analysis.has_button("New project", "Create", "New video"):
                return PluginResult(success=True, code="OK", reason="App home screen detected")
            err = ERRORS["APP_CLOSED"]
            return PluginResult(
                success=False,
                code=err.code,
                reason="App home screen not detected after launch",
                suggested_retry=err.suggested_retry,
            )

        await asyncio.sleep(4)
        return PluginResult(success=True, code="OK", reason="Launched (vision disabled)")

    # ── prepare ───────────────────────────────────────────────────────────────

    async def prepare(self, job: dict, adb_address: str, device_id: str) -> PluginResult:
        """Asset push is handled as explicit workflow steps — nothing extra needed."""
        return PluginResult(success=True, code="OK", reason="Ready")

    # ── execute ───────────────────────────────────────────────────────────────

    async def execute(self, job: dict, adb_address: str, device_id: str) -> PluginResult:
        """
        Build workflow and start execution.

        If job["simulate"] is True, return the planned step list without
        touching the Execution Engine or the device.
        """
        validation = await self.validate(job)
        if not validation.success:
            return validation

        steps = build_workflow(job, device_id=device_id)

        # ── Simulation mode ──────────────────────────────────────────────────
        if job.get("simulate", False):
            return PluginResult(
                success=True,
                code="SIMULATED",
                reason=f"Simulation complete: {len(steps)} steps planned",
                data={
                    "total_steps": len(steps),
                    "steps": [
                        {"type": s["type"], "label": s["label"]}
                        for s in steps
                    ],
                },
            )

        # ── Real execution ───────────────────────────────────────────────────
        from app.execution import executor
        from app.execution.models import ExecutionJob
        from app.models.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            db_job = ExecutionJob(
                content_job_id=job.get("content_job_id"),
                device_id=device_id,
                adb_address=adb_address,
                platform=self.app_id,
                post_type=job.get("post_type", "draft"),
                schedule_time=job.get("schedule_time"),
                video_prompt=job.get("video_prompt", ""),
                image_path=job.get("image_path", ""),
                status="STARTING",
            )
            db.add(db_job)
            await db.commit()
            await db.refresh(db_job)

        await executor.start_execution(
            job_id=db_job.id,
            device_id=device_id,
            adb_address=adb_address,
            steps=steps,
        )

        return PluginResult(
            success=True,
            code="STARTED",
            reason=f"Execution started: {len(steps)} steps",
            job_id=db_job.id,
            data={"total_steps": len(steps)},
        )

    # ── finish ────────────────────────────────────────────────────────────────

    async def finish(self, job: dict, adb_address: str, device_id: str) -> PluginResult:
        """Reserved for future post-execution cleanup (e.g. clearing temp files)."""
        return PluginResult(success=True, code="OK", reason="Finished")
