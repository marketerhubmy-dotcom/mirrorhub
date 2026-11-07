"""
YouTube Create plugin workflow builder.

Builds a step list that the Execution Engine can run.
Supports zero, one, or multiple reference images.
Callers never import step-type strings directly; they call build_workflow().
"""
from .constants import GENERATION_TIMEOUT, PREFERRED_RESOLUTION
from .image_manager import resolve_images, build_push_steps, build_add_images_step


def build_workflow(job: dict, device_id: str = "") -> list[dict]:
    """
    Build the complete YouTube Create step list from a job dict.

    Accepted job keys:
        video_prompt      str   — script / prompt text typed into the app
        image_path        str   — single reference image (legacy compat)
        image_paths       list  — multiple reference images (preferred)
        post_type         str   — "draft" | "post_now" | "schedule"
        schedule_time     str   — ISO datetime string when post_type="schedule"
        generation_timeout int  — override default GENERATION_TIMEOUT
        resolution        str   — preferred export resolution ("1080p" | default)
        style             str   — preferred visual style (informational)
        duration          str   — preferred duration in seconds (informational)
    """
    _d = {"device_id": device_id}
    images = resolve_images(job)
    post_type = job.get("post_type", "draft")
    schedule_time = job.get("schedule_time")
    script = job.get("video_prompt", "").strip()
    resolution = job.get("resolution", PREFERRED_RESOLUTION)
    generation_timeout = int(job.get("generation_timeout", GENERATION_TIMEOUT))

    steps: list[dict] = []

    # ── Phase IMPORT_IMAGES: push reference image(s) to device ────────────────
    if images:
        steps.extend(build_push_steps(images, device_id))

    # ── Phase OPEN_APP ─────────────────────────────────────────────────────────
    steps.append({
        "type": "ytcreate_launch",
        "label": "Buka YT Create",
        "retry_max": 3,
        **_d,
    })

    # ── Phase CREATE_PROJECT ──────────────────────────────────────────────────
    steps.append({
        "type": "ytcreate_new_project",
        "label": "New project",
        "retry_max": 3,
        **_d,
    })

    steps.append({
        "type": "ytcreate_select_script",
        "label": "Pilih Script mode",
        "retry_max": 2,
        **_d,
    })

    # ── Phase INPUT_PROMPT ────────────────────────────────────────────────────
    steps.append({
        "type": "ytcreate_paste_prompt",
        "script": script,
        "label": "Input script",
        "retry_max": 2,
        **_d,
    })

    # ── Phase IMPORT_IMAGES (gallery selection) ───────────────────────────────
    if images:
        if len(images) == 1:
            # Single-image path — uses the well-tested existing handler
            steps.append({
                "type": "ytcreate_add_image",
                "label": "Tambah gambar produk",
                "retry_max": 2,
                **_d,
            })
        else:
            steps.append(build_add_images_step(len(images), device_id))

    # ── Phase GENERATE ────────────────────────────────────────────────────────
    steps.append({
        "type": "ytcreate_generate",
        "label": "Generate video",
        "retry_max": 1,
        **_d,
    })

    # ── Phase WAIT_GENERATION ─────────────────────────────────────────────────
    steps.append({
        "type": "ytcreate_wait_generation",
        "wait_seconds": generation_timeout,
        "label": "Tunggu video siap",
        "retry_max": 1,
        **_d,
    })

    # ── Phase EXPORT ──────────────────────────────────────────────────────────
    if resolution == "1080p":
        steps.append({
            "type": "ytcreate_select_resolution",
            "resolution": resolution,
            "label": f"Pilih resolusi {resolution}",
            "retry_max": 1,
            **_d,
        })

    steps.append({
        "type": "ytcreate_export",
        "label": "Export video",
        "retry_max": 2,
        **_d,
    })

    # ── Phase SHARE ───────────────────────────────────────────────────────────
    steps.append({
        "type": "ytcreate_share",
        "label": "Share ke TikTok",
        "retry_max": 2,
        **_d,
    })

    # ── Phase DONE ────────────────────────────────────────────────────────────
    steps.append({
        "type": "ytcreate_post",
        "post_type": post_type,
        "schedule_time": schedule_time,
        "label": f"Post ({post_type})",
        "retry_max": 2,
        **_d,
    })

    return steps
