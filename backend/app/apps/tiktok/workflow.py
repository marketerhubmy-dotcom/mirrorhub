"""
TikTok Publisher plugin workflow builder.

Assembles the complete step list from a job dict.
All step-type strings are prefixed with 'tiktok_' to avoid collision
with YouTube Create handlers registered in the same execution engine.

If the job dict contains a 'workflow_id', the corresponding workflow is
loaded from the Workflow Manager (Release 0.6) and its steps are used
instead of the default built-in sequence.  This makes the flow editable.

Accepted job keys:
    video_path      str           — local path to the exported video
    caption         str           — post caption (may contain {{variables}})
    hashtags        list[str]     — hashtags without leading #
    first_comment   str           — optional first comment after publish
    product_id      str           — TikTok Shop product ID (optional)
    product         dict          — inline product dict (alternative to product_id)
    post_type       str           — "post_now" | "draft"  (default: "post_now")
    variables       dict          — {{placeholder}} values for caption resolution
    workflow_id     int           — Workflow Manager workflow ID (overrides default steps)
    content_job_id  int           — linked ContentJob ID (informational)
"""
from .uploader import build_upload_steps
from .publisher import build_caption_steps, build_product_steps, build_publish_steps
from .product import product_manager


def build_workflow(job: dict, device_id: str = "") -> list[dict]:
    """Build the complete TikTok publish step list from a job dict."""

    # ── Optional: load from Workflow Manager ──────────────────────────────────
    workflow_id = job.get("workflow_id")
    if workflow_id:
        return _load_from_workflow_manager(workflow_id, job, device_id)

    return _build_default(job, device_id)


def _build_default(job: dict, device_id: str) -> list[dict]:
    _d = {"device_id": device_id}
    video_path = job.get("video_path", "").strip()
    caption = job.get("caption", "")
    hashtags = job.get("hashtags", [])
    if isinstance(hashtags, str):
        hashtags = [t.strip() for t in hashtags.split(",") if t.strip()]
    first_comment = job.get("first_comment", "")
    post_type = job.get("post_type", "post_now")
    variables = job.get("variables") or {}

    steps: list[dict] = []

    # ── Phase OPEN_APP ────────────────────────────────────────────────────────
    steps.append({
        "type": "tiktok_launch",
        "label": "Buka TikTok",
        "retry_max": 3,
        **_d,
    })
    steps.append({
        "type": "tiktok_verify_home",
        "label": "Verify home screen",
        "retry_max": 2,
        **_d,
    })

    # ── Phase UPLOAD ──────────────────────────────────────────────────────────
    steps.extend(build_upload_steps(video_path, device_id))

    # ── Phase CAPTION ─────────────────────────────────────────────────────────
    if caption or hashtags:
        steps.extend(build_caption_steps(caption, hashtags, variables, device_id))

    # ── Phase PRODUCT ─────────────────────────────────────────────────────────
    product = product_manager.resolve(job)
    if product:
        steps.extend(build_product_steps(product, device_id))

    # ── Phases VALIDATION → PUBLISH → VERIFY ─────────────────────────────────
    steps.extend(build_publish_steps(post_type, first_comment, device_id))

    return steps


def _load_from_workflow_manager(workflow_id: int, job: dict, device_id: str) -> list[dict]:
    """
    Load workflow steps from the Workflow Manager DB and convert them to
    execution-engine step dicts with {{variable}} resolution applied.

    Falls back to _build_default() if the workflow is not found.
    """
    try:
        import asyncio
        from app.models.database import AsyncSessionLocal
        from app.workflows.repository import get_steps
        from app.workflows.player import _resolve_params

        variables = job.get("variables") or {}

        async def _fetch():
            async with AsyncSessionLocal() as db:
                return await get_steps(db, workflow_id)

        loop = asyncio.get_event_loop()
        db_steps = loop.run_until_complete(_fetch())

        if not db_steps:
            return _build_default(job, device_id)

        steps = []
        for s in db_steps:
            if not s.enabled:
                continue
            params = _resolve_params(s.parameters, variables)
            params["device_id"] = device_id
            steps.append({
                "type": s.step_type,
                "label": s.label,
                "retry_max": s.retry_max,
                **params,
            })
        return steps

    except Exception:
        return _build_default(job, device_id)
