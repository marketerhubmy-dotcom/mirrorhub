"""
TikTokPlugin — AppPlugin implementation for TikTok publishing.

Entry points:
    validate()  — check job dict before touching the device
    launch()    — open TikTok, confirm home screen via Vision Engine
    prepare()   — push video asset to device (pre-step setup)
    execute()   — validate → build steps → start Execution Engine
                  (or return planned steps in simulation mode)
    finish()    — reserved for post-execution cleanup

Simulation mode:
    Set job["simulate"] = True.  The plugin runs full validation + workflow
    build, then returns the planned steps WITHOUT calling the Execution Engine.

Logging:
    Every phase logs timestamp, current screen (via Vision Engine), and result.
"""
import asyncio
import subprocess

from app.apps.base import AppPlugin, PluginResult
from app.utils.adb_path import ADB
from .constants import PACKAGE_NAME, PACKAGE_NAME_ALT, LAUNCH_TIMEOUT
from .state import ERRORS
from .validator import validate, validate_product_job
from .workflow import build_workflow


class TikTokPlugin(AppPlugin):

    @property
    def app_id(self) -> str:
        return "tiktok"

    # ── validate ──────────────────────────────────────────────────────────────

    async def validate(self, job: dict) -> PluginResult:
        result = validate(job)
        if not result.success:
            return result
        return validate_product_job(job)

    # ── launch ────────────────────────────────────────────────────────────────

    async def launch(self, adb_address: str, device_id: str) -> PluginResult:
        """Open TikTok via ADB monkey, verify home screen with Vision Engine."""
        # Try primary package name; fall back to regional variant
        for package in (PACKAGE_NAME, PACKAGE_NAME_ALT):
            proc = await asyncio.create_subprocess_exec(
                str(ADB), "-s", adb_address,
                "shell", "monkey", "-p", package,
                "-c", "android.intent.category.LAUNCHER", "1",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            await proc.communicate()
            if proc.returncode == 0:
                break

        if device_id:
            from app.vision.analyzer import wait_until
            analysis = await wait_until(
                adb_address, device_id,
                button="For You",
                timeout=LAUNCH_TIMEOUT,
                poll_interval=2.0,
            )
            if analysis.has_button("For You", "Following", "Explore", "Create"):
                return PluginResult(success=True, code="OK", reason="TikTok home screen detected")
            err = ERRORS["APP_CLOSED"]
            return PluginResult(
                success=False,
                code=err.code,
                reason="TikTok home screen not detected after launch",
                suggested_retry=err.suggested_retry,
            )

        await asyncio.sleep(5)
        return PluginResult(success=True, code="OK", reason="Launched (vision disabled)")

    # ── prepare ───────────────────────────────────────────────────────────────

    async def prepare(self, job: dict, adb_address: str, device_id: str) -> PluginResult:
        """
        Validate the video file exists locally.
        Actual ADB push is handled as an explicit workflow step (tiktok_push_video).
        """
        from .uploader import validate_video_file
        info = validate_video_file(job.get("video_path", ""))
        if not info["valid"]:
            return PluginResult(
                success=False,
                code=ERRORS["VIDEO_MISSING"].code,
                reason=info["reason"],
                suggested_retry=False,
            )
        return PluginResult(
            success=True, code="OK",
            reason=f"Video ready ({info['size_bytes'] // 1024} KB, {info['extension']})",
        )

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
                post_type=job.get("post_type", "post_now"),
                schedule_time=job.get("schedule_time"),
                video_prompt=job.get("caption", ""),   # reuse video_prompt field for caption
                image_path=job.get("video_path", ""),  # reuse image_path field for video path
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
        """Reserved for post-execution cleanup (e.g. deleting temp video from device)."""
        return PluginResult(success=True, code="OK", reason="Finished")
