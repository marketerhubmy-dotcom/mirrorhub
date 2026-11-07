"""
Quick Launch API — paste TikTok Shop URL → pick angle/avatar → run full pipeline.

Two-phase flow (so the caller can pick a content angle / avatar before AI
generates the actual video prompt, instead of always getting angle #1):

  Phase 1 — POST /quicklaunch/scrape
    1. Validate + scrape product URL (TikTok Shop only)
    2. Download product image
    3. AI analyse product → tiktok_product_name, audience, benefits, angles
    4. Create ContentJob in DB (draft — no video_prompt yet)
    Returns {job_id, product_name, content_angles, ...} for the caller to choose from.

  Phase 2 — POST /quicklaunch/start
    5. Apply chosen angle / avatar / dialogue / own reference image to the job
    6. AI generate full content (video_prompt, caption, hashtags, cover_hook)
    7. Build 19+-step pipeline and start execution
    Returns {execution_job_id, content_job_id, total_steps}.
"""
import asyncio
import json
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_db
from app.services.product_scraper import validate_url, fetch_product, download_image
from app.services.ai_generator import generate_product_analysis, generate_avatar_questions
from app.content import repository, service
from app.content.schemas import ContentJobCreate, GenerateRequest, ContentJobUpdate
from app.content.models import ContentStatus
from app.content.avatars import get_avatar_description
from app.content.generator import generate_brief, generate_video_prompt

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/quicklaunch", tags=["quicklaunch"])

UPLOAD_DIR = Path(__file__).parent.parent.parent / "uploads"


class ScrapeResponse(BaseModel):
    job_id: int
    product_name: str
    tiktok_product_name: str
    image_filename: str
    target_audience: str
    key_benefits: list[str]
    content_angles: list[str]
    default_angle: str
    pain_points: list[str]
    desires: list[str]
    triggers: list[str]


class VariantsRequest(BaseModel):
    job_id: int
    angles: list[str]
    pain_points: list[str] = []
    desires: list[str] = []
    triggers: list[str] = []
    avatar: str = ""
    custom_avatar: str = ""
    dialogue: str = ""


class Variant(BaseModel):
    angle: str
    hook: str
    video_prompt: str


class VariantsResponse(BaseModel):
    variants: list[Variant]


class QuickLaunchResponse(BaseModel):
    execution_job_id: int
    content_job_id: int
    product_name: str
    tiktok_product_name: str
    total_steps: int
    status: str = "started"


async def _get_device(db: AsyncSession, device_id: str):
    from sqlalchemy import select
    from app.models.device import Device
    result = await db.execute(select(Device).where(Device.device_id == device_id))
    return result.scalar_one_or_none()


# ── Phase 1: scrape + analyse ───────────────────────────────────────────────

@router.post("/scrape", response_model=ScrapeResponse)
async def quick_launch_scrape(
    product_url: str = Body(..., embed=True),
    db: AsyncSession = Depends(get_db),
):
    ok, err = validate_url(product_url)
    if not ok:
        raise HTTPException(400, f"URL tidak sah: {err}")

    logger.info("quicklaunch: scraping %s", product_url)
    product_data = await fetch_product(product_url)

    if product_data.get("fetch_failed"):
        raise HTTPException(422, f"Gagal scrape produk: {product_data.get('fetch_error', 'unknown')}")

    product_title = product_data.get("title", "Produk TikTok Shop")
    image_url = product_data.get("image_url", "")

    image_filename: str | None = None
    if image_url:
        logger.info("quicklaunch: downloading product image")
        image_filename = await download_image(image_url)

    if not image_filename:
        raise HTTPException(422, "Gagal download gambar produk. Pastikan URL produk betul.")

    logger.info("quicklaunch: running AI product analysis")
    analysis = await asyncio.to_thread(generate_product_analysis, product_data)
    avatar_questions = await asyncio.to_thread(generate_avatar_questions, product_data)

    tiktok_product_name = analysis.get("tiktok_product_name") or product_title
    target_audience = analysis.get("target_audience", "")
    key_benefits = analysis.get("key_benefits", [])
    pain_points = analysis.get("common_pain_points", [])
    buying_motivations = analysis.get("buying_motivations", [])
    content_angles = analysis.get("suggested_content_angles", [])
    video_style = analysis.get("default_video_style", "lifestyle natural, UGC")
    default_angle = content_angles[0] if content_angles else ""
    avatar_pain_points = avatar_questions.get("pain_points", [])
    avatar_desires = avatar_questions.get("desires", [])
    avatar_triggers = avatar_questions.get("triggers", [])

    product_snapshot = {
        "product_name": product_title,
        "tiktok_product_name": tiktok_product_name,
        "description": product_data.get("description", ""),
        "price": product_data.get("price", ""),
        "shop_name": product_data.get("shop_name", ""),
        "target_audience": target_audience,
        "key_benefits": key_benefits,
        "pain_points": pain_points,
        "buying_motivations": buying_motivations,
        "suggested_content_angles": content_angles,
        "visual_style": video_style,
        "reference_image": image_filename,
        "selected_content_angle": default_angle,
        "video_type": "conversion",
        "avatar": "",
        "custom_avatar": "",
        "avatar_reference_image": "",
        "avatar_pain_points": avatar_pain_points,
        "avatar_desires": avatar_desires,
        "avatar_triggers": avatar_triggers,
    }

    job_create = ContentJobCreate(
        title=f"Quick Launch — {product_title[:60]}",
        product=product_title,
        audience=target_audience,
        tiktok_product_name=tiktok_product_name,
        publish_mode="manual",
        visual_style=video_style,
        duration="8s",
    )
    job = await repository.create_job(db, job_create)

    patch = ContentJobUpdate(
        reference_images=[image_filename],
        product_snapshot=product_snapshot,
        selected_content_angle=default_angle,
        video_type="conversion",
    )
    job = await repository.update_job(db, job, patch)

    return ScrapeResponse(
        job_id=job.id,
        product_name=product_title,
        tiktok_product_name=tiktok_product_name,
        image_filename=image_filename,
        target_audience=target_audience,
        key_benefits=key_benefits,
        content_angles=content_angles,
        default_angle=default_angle,
        pain_points=avatar_pain_points,
        desires=avatar_desires,
        triggers=avatar_triggers,
    )


# ── Phase 1b: generate variants for selected angles/traits ──────────────────

@router.post("/variants", response_model=VariantsResponse)
async def quick_launch_variants(req: VariantsRequest, db: AsyncSession = Depends(get_db)):
    """
    Generate one hook + video_prompt candidate per selected angle, mixing in the
    caller's chosen pain points / desires / triggers / avatar / dialogue — lets
    the caller compare a few variations before committing one via /start.
    """
    job = await service.get_job_or_404(db, req.job_id)
    snap: dict = json.loads(job.product_snapshot) if job.product_snapshot else {}

    angles = req.angles or ([snap.get("selected_content_angle")] if snap.get("selected_content_angle") else [])
    if not angles:
        raise HTTPException(400, "Pilih sekurang-kurangnya 1 angle.")

    avatar_desc = get_avatar_description(req.avatar, req.custom_avatar)
    pain_points = req.pain_points or snap.get("pain_points", [])
    buying_motivations = (req.desires + req.triggers) or snap.get("buying_motivations", [])

    base_ctx = {
        "product_name": snap.get("product_name", job.product),
        "product_description": snap.get("description", ""),
        "key_benefits": snap.get("key_benefits", []),
        "target_audience": snap.get("target_audience", ""),
        "pain_points": pain_points,
        "buying_motivations": buying_motivations,
        "video_type": snap.get("video_type", "conversion"),
        "visual_style": snap.get("visual_style", ""),
        "duration": job.duration or "8s",
        "avatar": avatar_desc,
        "custom_instructions": req.dialogue,
        "reference_image": snap.get("reference_image", ""),
    }

    async def _build_variant(angle: str) -> Variant:
        ctx = {**base_ctx, "content_angle": angle}
        brief = await asyncio.to_thread(generate_brief, ctx)
        ctx.update(brief)
        video_prompt = await asyncio.to_thread(generate_video_prompt, ctx)
        return Variant(angle=angle, hook=brief.get("hook", ""), video_prompt=video_prompt)

    variants = await asyncio.gather(*(_build_variant(a) for a in angles))
    return VariantsResponse(variants=list(variants))


# ── Phase 2: apply choices + generate + run pipeline ────────────────────────

@router.post("/start", response_model=QuickLaunchResponse)
async def quick_launch_start(
    job_id: int = Form(...),
    device_id: str = Form(...),
    publish_mode: str = Form("manual"),
    content_angle: str = Form(""),
    avatar: str = Form(""),
    custom_avatar: str = Form(""),
    dialogue: str = Form(""),
    chosen_hook: str = Form(""),
    chosen_video_prompt: str = Form(""),
    avatar_image: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_db),
):
    job = await service.get_job_or_404(db, job_id)

    device = await _get_device(db, device_id)
    if not device or not device.adb_address:
        raise HTTPException(404, "Device tidak jumpa atau tiada ADB address")

    from app.execution.device_session import is_device_busy, get_active_job
    if is_device_busy(device_id):
        active_id = get_active_job(device_id)
        raise HTTPException(409, f"Device busy — execution job {active_id} sedang running")

    # ── Save avatar reference image, if provided ─────────────────────────────
    avatar_image_filename: str | None = None
    if avatar_image is not None and avatar_image.filename:
        ext = Path(avatar_image.filename).suffix or ".jpg"
        avatar_image_filename = f"{uuid.uuid4().hex}{ext}"
        (UPLOAD_DIR / avatar_image_filename).write_bytes(await avatar_image.read())

    snap: dict = json.loads(job.product_snapshot) if job.product_snapshot else {}
    image_filename = snap.get("reference_image") or (json.loads(job.reference_images or "[]") or [None])[0]
    if not image_filename:
        raise HTTPException(422, "Job ini tiada gambar produk — scrape URL semula.")

    reference_images = [image_filename]
    if avatar_image_filename:
        reference_images.append(avatar_image_filename)

    chosen_angle = content_angle.strip() or snap.get("selected_content_angle", "")
    snap["avatar"] = avatar
    snap["custom_avatar"] = custom_avatar
    snap["avatar_reference_image"] = avatar_image_filename or ""
    snap["selected_content_angle"] = chosen_angle

    has_chosen_variant = bool(chosen_video_prompt.strip())

    patch = ContentJobUpdate(
        publish_mode=publish_mode,
        avatar=avatar,
        custom_instructions=dialogue,
        reference_images=reference_images,
        product_snapshot=snap,
        selected_content_angle=chosen_angle,
        **({"video_prompt": chosen_video_prompt.strip(), "hook": chosen_hook.strip()}
           if has_chosen_variant else {}),
    )
    job = await repository.update_job(db, job, patch)

    # ── AI generate content ──────────────────────────────────────────────────
    # If the caller already picked a variant from /variants, keep that exact
    # hook/video_prompt as-is and only generate the remaining fields.
    logger.info("quicklaunch: generating AI content for job %d (angle=%r, chosen_variant=%s)",
                job.id, chosen_angle, has_chosen_variant)
    job = await service.generate_content(db, job, GenerateRequest(
        brief=not has_chosen_variant,
        video_prompt=not has_chosen_variant,
    ))

    if not job.video_prompt and not job.hook:
        raise HTTPException(500, "AI gagal generate video prompt. Semak OPENAI_API_KEY.")

    # ── Build & start pipeline ───────────────────────────────────────────────
    from app.execution.models import ExecutionJob
    from app.execution.executor import start_execution
    from app.execution.preflight import run_preflight

    product_title = job.product
    tiktok_product_name = job.tiktok_product_name or ""
    image_path = str(UPLOAD_DIR / image_filename)
    hashtags: list[str] = json.loads(job.hashtags or "[]")
    base_caption = (job.caption or "").strip()
    hash_suffix = " ".join(hashtags).strip() if hashtags else ""
    full_caption = f"{base_caption}\n{hash_suffix}".strip() if base_caption else hash_suffix
    cover_hook = (job.cover_hook or "").strip()
    tiktok_product = tiktok_product_name.strip()

    preflight = await run_preflight(
        adb_address=device.adb_address,
        video_prompt=job.video_prompt or job.hook or "",
        caption=full_caption,
        image_local_path=image_path,
        tiktok_product_name=tiktok_product,
        publish_mode=publish_mode,
    )
    if not preflight.ok:
        raise HTTPException(422, "Preflight gagal:\n" + "\n".join(f"• {e}" for e in preflight.errors))

    _d = {"device_id": device_id}
    device_dir = "/sdcard/DCIM/mirrorhub"
    device_filename = f"mh_job{job.id}.jpg"
    device_image = f"{device_dir}/{device_filename}"
    has_avatar_image = bool(avatar_image_filename)

    approved_prompt = (
        job.video_prompt
        or "\n".join(p for p in [job.hook, job.story, job.cta] if p)
    ).strip()

    steps: list[dict] = [
        {"type": "ytcreate_push_image", "local": image_path,
         "device_dir": device_dir, "device_filename": device_filename,
         "job_id": str(job.id), "label": "Upload image ke phone", "retry_max": 2, **_d},
    ]
    if has_avatar_image:
        steps.append({
            "type": "ytcreate_push_image_file",
            "local": str(UPLOAD_DIR / avatar_image_filename),
            "device_dir": device_dir,
            "device_filename": f"mh_avatar_job{job.id}.jpg",
            "cleanup_pattern": "mh_avatar_job*.jpg",
            "label": "Upload gambar avatar ke phone", "retry_max": 2, **_d,
        })
    steps += [
        {"type": "ytcreate_launch",      "label": "Buka YT Create",    "retry_max": 3, **_d},
        {"type": "ytcreate_new_project", "label": "New project",        "retry_max": 3, **_d},
        {"type": "ytcreate_add_image",   "device_path": device_image,
         "count": 2 if has_avatar_image else 1,
         "label": "Tambah reference image" + (" + avatar" if has_avatar_image else ""),
         "retry_max": 2, **_d},
        {"type": "ytcreate_paste_prompt", "script": approved_prompt,
         "script_char_count": len(approved_prompt),
         "label": "Input video prompt", "retry_max": 2, **_d},
        {"type": "ytcreate_generate",        "label": "Jana video AI",    "retry_max": 1, **_d},
        {"type": "ytcreate_wait_generation", "wait_seconds": 300,
         "label": "Tunggu video siap",       "retry_max": 1, **_d},
        {"type": "ytcreate_export",          "label": "Export video",     "retry_max": 2, **_d},
        {"type": "ytcreate_share",           "label": "Share ke TikTok",  "retry_max": 2, **_d},
        {"type": "tiktok_advance_to_post_editor", "label": "Masuk post editor", "retry_max": 2, **_d},
        {"type": "tiktok_edit_cover", "cover_hook": cover_hook,
         "label": "Edit cover TikTok", "retry_max": 1, **_d},
    ]

    if full_caption:
        steps.append({
            "type": "tiktok_insert_caption", "caption": full_caption,
            "caption_char_count": len(full_caption),
            "label": "Insert caption + hashtags", "retry_max": 2, **_d,
        })

    if tiktok_product and publish_mode != "draft":
        steps += [
            {"type": "tiktok_open_product_selector", "label": "Buka Add Link → Product",
             "retry_max": 2, **_d},
            {"type": "tiktok_wait_product_page", "wait_seconds": 45,
             "label": "Tunggu TikTok Shop", "retry_max": 2, **_d},
            {"type": "tiktok_search_product", "search_term": tiktok_product,
             "label": f"Cari: {tiktok_product}", "retry_max": 2, **_d},
            {"type": "tiktok_match_product", "product_name": tiktok_product,
             "label": "Match produk", "retry_max": 2, **_d},
            {"type": "tiktok_attach_product", "product_name": tiktok_product,
             "label": "Lampirkan beg kuning", "retry_max": 2, **_d},
            {"type": "tiktok_verify_product", "product_name": tiktok_product,
             "label": "Verify beg kuning", "retry_max": 2, **_d},
        ]

    steps.append({"type": "tiktok_pre_publish_check", "label": "Semak sebelum post",
                  "retry_max": 2, **_d})

    if publish_mode == "auto":
        steps += [
            {"type": "tiktok_publish", "post_type": "post_now",
             "label": "Publish ke TikTok", "retry_max": 2, **_d},
            {"type": "tiktok_verify_success", "label": "Verify posting success",
             "retry_max": 2, **_d},
        ]
    elif publish_mode == "draft":
        steps.append(
            {"type": "tiktok_publish", "post_type": "draft",
             "label": "💾 Simpan sebagai draft TikTok", "retry_max": 2, **_d}
        )

    db_exec = ExecutionJob(
        content_job_id=job.id,
        device_id=device_id,
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
        device_id=device_id,
        adb_address=device.adb_address,
        steps=steps,
    )

    await repository.set_status(db, job, ContentStatus.WAITING_GENERATION)

    logger.info(
        "quicklaunch: started execution_job=%d content_job=%d steps=%d product='%s'",
        db_exec.id, job.id, len(steps), tiktok_product_name,
    )

    return QuickLaunchResponse(
        execution_job_id=db_exec.id,
        content_job_id=job.id,
        product_name=product_title,
        tiktok_product_name=tiktok_product_name,
        total_steps=len(steps),
    )
