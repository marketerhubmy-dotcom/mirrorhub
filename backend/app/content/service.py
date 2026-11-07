"""
Orchestrates repository + generator for Content Pipeline — MVP 0.6.1.
Builds a ProductContentContext dict from the job + optional context override
and passes it to every generator function.
"""
import asyncio
import json
import logging

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.content import generator, repository
from app.content.models import ContentJob, ContentStatus
from app.content.schemas import ContentJobCreate, ContentJobUpdate, GenerateRequest
from app.content.avatars import get_avatar_description

logger = logging.getLogger(__name__)


def _build_context(job_dict: dict, override: dict | None = None) -> dict:
    """
    Merge job fields + product_snapshot + optional request-level context override
    into a flat context dict used by all generator functions.

    Priority (highest wins): override > job direct columns > product_snapshot.
    Logs context field names and lengths (not values) to satisfy security constraint.
    """
    snap: dict = job_dict.get("product_snapshot") or {}

    # video_type and selected_content_angle: prefer direct job columns, fall back to snapshot
    video_type = (
        job_dict.get("video_type", "")
        or snap.get("video_type", "")
    )
    content_angle = (
        job_dict.get("selected_content_angle", "")
        or snap.get("selected_content_angle", "")
        or job_dict.get("topic", "")
    )
    avatar_name = job_dict.get("avatar", "") or snap.get("avatar", "")

    ctx = {
        # Product identity
        "product_name":        snap.get("product_name") or job_dict.get("product", ""),
        "product_description": snap.get("description", ""),
        "key_benefits":        snap.get("key_benefits", []),
        "target_audience":     snap.get("target_audience") or job_dict.get("audience", ""),
        "pain_points":         snap.get("pain_points", []) or snap.get("common_pain_points", []),
        "buying_motivations":  snap.get("buying_motivations", []),
        # Content choices — direct job columns take priority
        "video_type":    video_type,
        "content_angle": content_angle,
        "visual_style":  job_dict.get("visual_style", "") or snap.get("visual_style", ""),
        "duration":      job_dict.get("duration", "8s"),
        # Avatar — expand preset name to its full description string
        "avatar": get_avatar_description(avatar_name, snap.get("custom_avatar", "")),
        "reference_image": (
            snap.get("reference_image")
            or (json.loads(job_dict.get("reference_images_raw") or "[]") or [""])[0]
        ),
        "avatar_reference_image": snap.get("avatar_reference_image", ""),
        "custom_instructions": job_dict.get("custom_instructions", ""),
        # Generated brief (populated after generate_brief runs)
        "hook":  job_dict.get("hook", ""),
        "story": job_dict.get("story", ""),
        "cta":   job_dict.get("cta", ""),
        # Legacy fallbacks for old jobs without a snapshot
        "product":   job_dict.get("product", ""),
        "audience":  job_dict.get("audience", ""),
        "topic":     job_dict.get("topic", ""),
    }

    if override:
        ctx.update(override)

    # Log field names + lengths only (never log full content values)
    logger.debug(
        "AI context built: %s",
        {k: len(str(v)) if v else 0 for k, v in ctx.items()},
    )

    return ctx


def _validate_outputs(update_data: dict, product_name: str) -> list[str]:
    """
    Lightweight validation of AI-generated content.
    Returns a list of warning strings; empty list = all OK.
    Does NOT raise — caller decides whether to reject.
    """
    warnings: list[str] = []

    vp = update_data.get("video_prompt", "")
    if vp:
        if len(vp) < 30:
            warnings.append(f"video_prompt suspiciously short ({len(vp)} chars)")
        # Must reference the product name (case-insensitive, first word of name is enough)
        first_word = (product_name or "").split()[0].lower() if product_name else ""
        if first_word and first_word not in vp.lower():
            warnings.append(
                f"video_prompt does not mention product key term '{first_word}'"
            )

    ch = update_data.get("cover_hook", "")
    if ch:
        lines = [l for l in ch.strip().splitlines() if l.strip()]
        if len(lines) > 3:
            warnings.append(f"cover_hook has {len(lines)} lines (max 3)")
        if ch != ch.upper():
            warnings.append("cover_hook is not UPPERCASE")

    cap = update_data.get("caption", "")
    if cap and len(cap) < 10:
        warnings.append(f"caption suspiciously short ({len(cap)} chars)")

    tags = update_data.get("hashtags", [])
    if tags is not None:
        if len(tags) < 3:
            warnings.append(f"only {len(tags)} hashtag(s) generated (need 3–5)")
        if len(tags) > 5:
            warnings.append(f"{len(tags)} hashtags generated — will be trimmed to 5")
            update_data["hashtags"] = tags[:5]

    return warnings


async def create_job(db: AsyncSession, data: ContentJobCreate) -> ContentJob:
    return await repository.create_job(db, data)


async def get_job_or_404(db: AsyncSession, job_id: int) -> ContentJob:
    job = await repository.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="ContentJob tidak jumpa")
    return job


async def generate_content(
    db: AsyncSession,
    job: ContentJob,
    req: GenerateRequest,
) -> ContentJob:
    """Run AI pipeline stages. All generators receive the full product context."""
    job_dict = job.to_dict()
    # Attach raw reference_images for _build_context
    job_dict["reference_images_raw"] = job.reference_images

    ctx_override = req.context.model_dump() if req.context else None
    ctx = _build_context(job_dict, ctx_override)

    update_data: dict = {}

    if req.brief:
        brief = await asyncio.to_thread(generator.generate_brief, ctx)
        update_data.update(brief)
        ctx.update(brief)  # downstream prompts see the fresh brief

    if req.video_prompt:
        update_data["video_prompt"] = await asyncio.to_thread(
            generator.generate_video_prompt, ctx
        )

    if req.cover_hook:
        update_data["cover_hook"] = await asyncio.to_thread(
            generator.generate_cover_hook, ctx
        )

    if req.caption:
        update_data["caption"] = await asyncio.to_thread(generator.generate_caption, ctx)

    if req.hashtags:
        update_data["hashtags"] = await asyncio.to_thread(generator.generate_hashtags, ctx)

    # Lightweight validation — log warnings but do not block the save
    product_name = ctx.get("product_name", "")
    warnings = _validate_outputs(update_data, product_name)
    if warnings:
        logger.warning("AI output validation warnings for job %d: %s", job.id, warnings)

    has_prompt = bool(update_data.get("video_prompt") or job.video_prompt)
    update_data["status"] = (
        ContentStatus.PROMPT_READY if has_prompt else ContentStatus.BRIEF
    )

    patch = ContentJobUpdate(**update_data)
    return await repository.update_job(db, job, patch)


async def add_reference_image(db: AsyncSession, job: ContentJob, filename: str) -> ContentJob:
    return await repository.append_image(db, job, filename)
