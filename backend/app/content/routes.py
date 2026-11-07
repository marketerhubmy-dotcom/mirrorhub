import json
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException, UploadFile, File
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_db
from app.devices.registry import get_device
from app.services import automation_runner
from app.content import repository, service
from app.content.models import ContentStatus
from app.content.schemas import (
    ContentJobCreate,
    ContentJobUpdate,
    ContentJobResponse,
    GenerateRequest,
    WorkflowRequest,
    WorkflowResponse,
    PipelineRequest,
)
from app.content.workflow import build_content_workflow
from app.utils.paths import UPLOAD_DIR

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/content", tags=["content"])


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.post("/jobs", response_model=ContentJobResponse, status_code=201)
async def create_job(data: ContentJobCreate, db: AsyncSession = Depends(get_db)):
    job = await service.create_job(db, data)
    return job.to_dict()


@router.get("/jobs", response_model=list[ContentJobResponse])
async def list_jobs(db: AsyncSession = Depends(get_db)):
    jobs = await repository.list_jobs(db)
    return [j.to_dict() for j in jobs]


@router.get("/avatars")
async def list_avatar_presets():
    from app.content.avatars import list_presets
    return {"presets": list_presets()}


@router.get("/jobs/{job_id}", response_model=ContentJobResponse)
async def get_job(job_id: int, db: AsyncSession = Depends(get_db)):
    job = await service.get_job_or_404(db, job_id)
    return job.to_dict()


@router.patch("/jobs/{job_id}", response_model=ContentJobResponse)
async def update_job(
    job_id: int,
    data: ContentJobUpdate,
    db: AsyncSession = Depends(get_db),
):
    job = await service.get_job_or_404(db, job_id)
    job = await repository.update_job(db, job, data)
    return job.to_dict()


@router.delete("/jobs/{job_id}", status_code=204)
async def delete_job(job_id: int, db: AsyncSession = Depends(get_db)):
    await repository.delete_job(db, job_id)


# ── Status ────────────────────────────────────────────────────────────────────

@router.patch("/jobs/{job_id}/status", response_model=ContentJobResponse)
async def update_status(
    job_id: int,
    status: ContentStatus,
    db: AsyncSession = Depends(get_db),
):
    job = await service.get_job_or_404(db, job_id)
    job = await repository.set_status(db, job, status)
    return job.to_dict()


# ── AI Generation ─────────────────────────────────────────────────────────────

@router.post("/jobs/{job_id}/generate", response_model=ContentJobResponse)
async def generate_content(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    req: GenerateRequest | None = Body(default=None),
):
    """Run AI pipeline. Body is optional — omit to generate everything."""
    job = await service.get_job_or_404(db, job_id)
    job = await service.generate_content(db, job, req or GenerateRequest())
    return job.to_dict()


@router.post("/jobs/{job_id}/regenerate/{field}", response_model=ContentJobResponse)
async def regenerate_field(
    job_id: int,
    field: str,
    db: AsyncSession = Depends(get_db),
    req: GenerateRequest | None = Body(default=None),
):
    """
    Regenerate a single field: video_prompt | cover_hook | caption | hashtags | brief.
    Accepts optional GenerateRequest body to pass a ProductContentContext override.
    """
    ALLOWED = {"brief", "video_prompt", "cover_hook", "caption", "hashtags"}
    if field not in ALLOWED:
        from fastapi import HTTPException
        raise HTTPException(400, f"Field '{field}' tidak dibenarkan. Pilih: {ALLOWED}")

    base = GenerateRequest(
        brief=field == "brief",
        video_prompt=field == "video_prompt",
        cover_hook=field == "cover_hook",
        caption=field == "caption",
        hashtags=field == "hashtags",
        context=(req.context if req else None),
    )
    job = await service.get_job_or_404(db, job_id)
    job = await service.generate_content(db, job, base)
    return job.to_dict()


# ── Reference Images ──────────────────────────────────────────────────────────

@router.post("/jobs/{job_id}/images", response_model=ContentJobResponse)
async def upload_image(
    job_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    job = await service.get_job_or_404(db, job_id)
    ext = Path(file.filename or "image.jpg").suffix or ".jpg"
    filename = f"{uuid.uuid4().hex}{ext}"
    (UPLOAD_DIR / filename).write_bytes(await file.read())
    job = await service.add_reference_image(db, job, filename)
    return job.to_dict()


@router.delete("/jobs/{job_id}/images/{filename}", response_model=ContentJobResponse)
async def remove_image(
    job_id: int,
    filename: str,
    db: AsyncSession = Depends(get_db),
):
    job = await service.get_job_or_404(db, job_id)
    images: list[str] = json.loads(job.reference_images or "[]")
    images = [i for i in images if i != filename]
    patch = ContentJobUpdate(reference_images=images)
    job = await repository.update_job(db, job, patch)
    return job.to_dict()


# ── Workflow ──────────────────────────────────────────────────────────────────

@router.post("/jobs/{job_id}/workflow", response_model=WorkflowResponse)
async def get_workflow(
    job_id: int,
    req: WorkflowRequest,
    db: AsyncSession = Depends(get_db),
):
    """Build automation steps from ContentJob without running them."""
    job = await service.get_job_or_404(db, job_id)

    if not job.video_prompt and not job.hook:
        raise HTTPException(
            status_code=400,
            detail="Generate content dulu sebelum buat workflow",
        )

    images: list[str] = json.loads(job.reference_images or "[]")
    if not images:
        raise HTTPException(status_code=400, detail="Tambah reference image dulu")

    image_path = str(UPLOAD_DIR / images[0])
    steps = build_content_workflow(
        job=job,
        image_local_path=image_path,
        platform=req.platform,
        post_type=req.post_type,
        schedule_time=req.schedule_time,
    )
    return WorkflowResponse(steps=steps, total_steps=len(steps))


@router.post("/jobs/{job_id}/run")
async def run_workflow(
    job_id: int,
    req: WorkflowRequest,
    db: AsyncSession = Depends(get_db),
):
    """Build workflow steps and hand off to AutomationRunner."""
    job = await service.get_job_or_404(db, job_id)

    if not job.video_prompt and not job.hook:
        raise HTTPException(
            status_code=400,
            detail="Generate content dulu sebelum run",
        )

    images: list[str] = json.loads(job.reference_images or "[]")
    if not images:
        raise HTTPException(status_code=400, detail="Tambah reference image dulu")

    device = await get_device(db, req.device_id)
    if not device or not device.adb_address:
        raise HTTPException(status_code=404, detail="Device tidak jumpa atau tiada ADB address")

    image_path = str(UPLOAD_DIR / images[0])
    steps = build_content_workflow(
        job=job,
        image_local_path=image_path,
        platform=req.platform,
        post_type=req.post_type,
        schedule_time=req.schedule_time,
    )

    await automation_runner.start(req.device_id, device.adb_address, steps)

    # Advance status
    await repository.set_status(db, job, ContentStatus.WAITING_GENERATION)

    return {"status": "started", "total_steps": len(steps), "job_id": job_id}


# ── Full Pipeline (YouTube Create → TikTok) ───────────────────────────────────

@router.post("/jobs/{job_id}/run_pipeline")
async def run_pipeline(
    job_id: int,
    req: PipelineRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Build and start the combined YouTube Create → TikTok pipeline.

    Steps (in order):
      1. Push reference image to device
      2. Open YouTube Create, paste prompt, add image, generate, wait, export, share
      3. TikTok opens (via share sheet) with video loaded
      4. Insert caption + hashtags
      5. Attach TikTok Shop product (if configured)
      6. Stop at Publish button (manual mode) OR tap Publish (auto mode)
    """
    from app.execution.models import ExecutionJob
    from app.execution.device_session import is_device_busy, get_active_job
    from app.execution.executor import start_execution

    job = await service.get_job_or_404(db, job_id)

    if not job.video_prompt and not job.hook:
        raise HTTPException(400, "Generate content dulu sebelum run pipeline")

    images: list[str] = json.loads(job.reference_images or "[]")
    if not images:
        raise HTTPException(400, "Tambah reference image dulu")

    device = await get_device(db, req.device_id)
    if not device or not device.adb_address:
        raise HTTPException(404, "Device tidak jumpa atau tiada ADB address")

    if is_device_busy(req.device_id):
        active_id = get_active_job(req.device_id)
        raise HTTPException(409, f"Device busy — execution job {active_id} sedang running")

    image_path = str(UPLOAD_DIR / images[0])
    hashtags: list[str] = json.loads(job.hashtags or "[]")
    # Build final caption exactly as approved: caption.strip() + "\n" + "#tag1 #tag2..."
    base_caption = (job.caption or "").strip()
    hash_suffix  = " ".join(hashtags).strip() if hashtags else ""
    full_caption = f"{base_caption}\n{hash_suffix}".strip() if base_caption else hash_suffix

    tiktok_product = (job.tiktok_product_name or "").strip()
    cover_hook     = (job.cover_hook or "").strip()
    publish_mode   = req.publish_mode or job.publish_mode or "manual"

    # Log execution payload field names + lengths (not full values)
    logger.info(
        "Pipeline payload job=%d: prompt=%d chars, caption=%d chars, cover_hook=%d chars, "
        "hashtags=%d, tiktok_product=%d chars, image=%s",
        job_id,
        len(job.video_prompt or ""),
        len(full_caption),
        len(cover_hook),
        len(hashtags),
        len(tiktok_product),
        Path(image_path).name,
    )

    # ── Preflight: validate device + job state before building steps ─────────
    from app.execution.preflight import run_preflight
    preflight = await run_preflight(
        adb_address=device.adb_address,
        video_prompt=job.video_prompt or job.hook or "",
        caption=full_caption,
        image_local_path=image_path,
        tiktok_product_name=tiktok_product,
        publish_mode=publish_mode,
    )
    if not preflight.ok:
        raise HTTPException(
            422,
            detail="Preflight gagal:\n" + "\n".join(f"• {e}" for e in preflight.errors),
        )

    # ── Job-ID–specific image filename ───────────────────────────────────────
    device_dir      = "/sdcard/DCIM/mirrorhub"
    device_filename = f"mh_job{job_id}.jpg"
    device_image    = f"{device_dir}/{device_filename}"

    _d = {"device_id": req.device_id}

    approved_prompt = (
        job.video_prompt
        or "\n".join(p for p in [job.hook, job.story, job.cta] if p)
    ).strip()

    steps: list[dict] = [
        # ── Step 1: Push reference image ────────────────────────────────────
        {
            "type": "ytcreate_push_image",
            "local": image_path,
            "device_dir": device_dir,
            "device_filename": device_filename,
            "job_id": str(job_id),
            "label": "Upload image ke phone",
            "retry_max": 2, **_d,
        },

        # ── Step 2: YouTube Create ───────────────────────────────────────────
        {"type": "ytcreate_launch",      "label": "Buka YT Create",    "retry_max": 3, **_d},
        {"type": "ytcreate_new_project", "label": "New project",        "retry_max": 3, **_d},
        # add_image BEFORE paste_prompt — YTC clears the text field when gallery opens.
        {"type": "ytcreate_add_image",   "device_path": device_image,
         "label": "Tambah reference image", "retry_max": 2, **_d},
        {
            "type": "ytcreate_paste_prompt",
            "script": approved_prompt,
            "script_char_count": len(approved_prompt),   # for execution log
            "label": "Input video prompt yang diluluskan",
            "retry_max": 2, **_d,
        },
        {"type": "ytcreate_generate",        "label": "Jana video AI",          "retry_max": 1, **_d},
        {"type": "ytcreate_wait_generation", "wait_seconds": 300,
         "label": "Tunggu video siap",        "retry_max": 1, **_d},
        {"type": "ytcreate_export",          "label": "Export video",            "retry_max": 2, **_d},
        {"type": "ytcreate_share",           "label": "Share ke TikTok",         "retry_max": 2, **_d},

        # ── Step 10: Navigate past TikTok video editor to post details ───────
        # UIAutomator cannot see TikTok's custom video editor views, so we tap
        # the "Next" button at its known coordinate until the post editor appears.
        {"type": "tiktok_advance_to_post_editor",
         "label": "Masuk editor post TikTok",
         "retry_max": 2, **_d},

        # ── Step 11: TikTok cover — SKIP-safe ───────────────────────────────
        {
            "type": "tiktok_edit_cover",
            "cover_hook": cover_hook,
            "label": "Edit cover TikTok",
            "retry_max": 1, **_d,
        },
    ]

    # ── Step 11: Caption + hashtags ─────────────────────────────────────────
    if full_caption:
        steps.append({
            "type": "tiktok_insert_caption",
            "caption": full_caption,
            "caption_char_count": len(full_caption),   # for execution log
            "label": "Insert caption + hashtags",
            "retry_max": 2, **_d,
        })

    # ── Steps 12–17: TikTok Shop product attachment ──────────────────────────
    # Skipped in draft mode: beg kuning is geo-locked and reliably fails under
    # VPN, which would abort the whole pipeline before it ever saves the draft.
    # User attaches the product manually after turning VPN off.
    if tiktok_product and publish_mode != "draft":
        steps += [
            {"type": "tiktok_open_product_selector",
             "label": "Buka Add Link → Product",
             "retry_max": 2, **_d},
            {"type": "tiktok_wait_product_page", "wait_seconds": 45,
             "label": "Tunggu TikTok Shop memuatkan",
             "retry_max": 2, **_d},
            {"type": "tiktok_search_product", "search_term": tiktok_product,
             "label": f"Cari: {tiktok_product}",
             "retry_max": 2, **_d},
            {"type": "tiktok_match_product", "product_name": tiktok_product,
             "label": "Match hasil tepat",
             "retry_max": 2, **_d},
            {"type": "tiktok_attach_product", "product_name": tiktok_product,
             "label": "Lampirkan produk",
             "retry_max": 2, **_d},
            {"type": "tiktok_verify_product", "product_name": tiktok_product,
             "label": "Verify produk beg kuning dilampirkan",
             "retry_max": 2, **_d},
        ]

    # ── Step 18: Pre-publish check ───────────────────────────────────────────
    steps.append({"type": "tiktok_pre_publish_check", "label": "Semak sebelum post",
                  "retry_max": 2, **_d})

    if publish_mode == "auto":
        steps += [
            {"type": "tiktok_publish", "post_type": "post_now",
             "label": "🚀 Publish ke TikTok", "retry_max": 2, **_d},
            {"type": "tiktok_verify_success",
             "label": "Verify posting success", "retry_max": 2, **_d},
        ]
    elif publish_mode == "draft":
        # VPN geo-lock workaround: save as a real TikTok draft instead of just
        # parking the pipeline at the pre-publish screen. User later disables
        # VPN, opens Drafts, attaches beg kuning manually, and posts.
        steps.append(
            {"type": "tiktok_publish", "post_type": "draft",
             "label": "💾 Simpan sebagai draft TikTok", "retry_max": 2, **_d}
        )

    db_exec = ExecutionJob(
        content_job_id=job_id,
        device_id=req.device_id,
        adb_address=device.adb_address,
        platform="ytcreate_tiktok_pipeline",
        post_type={"auto": "post_now", "draft": "draft"}.get(publish_mode, "manual"),
        video_prompt=job.video_prompt or job.hook or "",
        image_path=image_path,
        status="STARTING",
    )
    db.add(db_exec)
    await db.commit()
    await db.refresh(db_exec)

    await start_execution(
        job_id=db_exec.id,
        device_id=req.device_id,
        adb_address=device.adb_address,
        steps=steps,
    )

    await repository.set_status(db, job, ContentStatus.WAITING_GENERATION)

    return {
        "status": "started",
        "execution_job_id": db_exec.id,
        "total_steps": len(steps),
    }


@router.get("/jobs/{job_id}/latest_execution")
async def latest_execution(job_id: int, db: AsyncSession = Depends(get_db)):
    """Return the most recent execution job for this content job (live state if active)."""
    from app.execution.models import ExecutionJob
    from app.execution.executor import get_state

    result = await db.execute(
        select(ExecutionJob)
        .where(ExecutionJob.content_job_id == job_id)
        .order_by(ExecutionJob.created_at.desc())
        .limit(1)
    )
    exec_job = result.scalar_one_or_none()
    if not exec_job:
        return None

    # Prefer live in-memory state over stale DB row
    live = get_state(exec_job.id)
    if live:
        return live.to_dict()
    return exec_job.to_dict()
