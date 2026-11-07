import json
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.content.models import ContentJob, ContentStatus
from app.content.schemas import ContentJobCreate, ContentJobUpdate


async def create_job(db: AsyncSession, data: ContentJobCreate) -> ContentJob:
    job = ContentJob(
        title=data.title,
        topic=data.topic,
        objective=data.objective,
        audience=data.audience,
        product=data.product,
        duration=data.duration,
        visual_style=data.visual_style,
        status=ContentStatus.IDEA,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


async def get_job(db: AsyncSession, job_id: int) -> ContentJob | None:
    result = await db.execute(select(ContentJob).where(ContentJob.id == job_id))
    return result.scalar_one_or_none()


async def list_jobs(db: AsyncSession) -> list[ContentJob]:
    result = await db.execute(
        select(ContentJob).order_by(ContentJob.updated_at.desc())
    )
    return list(result.scalars().all())


async def update_job(db: AsyncSession, job: ContentJob, data: ContentJobUpdate) -> ContentJob:
    for field, value in data.model_dump(exclude_none=True).items():
        if field in ("hashtags", "reference_images", "product_snapshot"):
            setattr(job, field, json.dumps(value, ensure_ascii=False))
        else:
            setattr(job, field, value)
    await db.commit()
    await db.refresh(job)
    return job


async def set_status(db: AsyncSession, job: ContentJob, status: ContentStatus) -> ContentJob:
    job.status = status
    await db.commit()
    await db.refresh(job)
    return job


async def append_image(db: AsyncSession, job: ContentJob, filename: str) -> ContentJob:
    images: list[str] = json.loads(job.reference_images or "[]")
    images.append(filename)
    job.reference_images = json.dumps(images, ensure_ascii=False)
    await db.commit()
    await db.refresh(job)
    return job


async def delete_job(db: AsyncSession, job_id: int) -> None:
    job = await get_job(db, job_id)
    if job:
        await db.delete(job)
        await db.commit()
