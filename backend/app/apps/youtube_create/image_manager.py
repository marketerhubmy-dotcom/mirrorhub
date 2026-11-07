"""
Reference image handling for the YouTube Create plugin.

Supports zero, one, or multiple reference images.  Generates the correct
step types so the Execution Engine can push and select each one.
"""
from .constants import DEVICE_IMAGE_DIR


def resolve_images(job: dict) -> list[str]:
    """Return canonical list of local image paths from a job dict."""
    images = job.get("image_paths", [])
    if isinstance(images, str):
        images = [images]
    if not images:
        single = job.get("image_path", "")
        if single:
            images = [single]
    return [str(p) for p in images if p]


def build_push_steps(images: list[str], device_id: str = "") -> list[dict]:
    """One ytcreate_push_image_file step per image, with unique device filenames."""
    _d = {"device_id": device_id}
    steps = []
    for i, local_path in enumerate(images):
        filename = f"mh_image_{i:02d}.jpg"
        steps.append({
            "type": "ytcreate_push_image_file",
            "local": local_path,
            "device_filename": filename,
            "device_dir": DEVICE_IMAGE_DIR,
            "label": f"Upload gambar {i + 1}/{len(images)}",
            "retry_max": 2,
            **_d,
        })
    return steps


def build_add_images_step(count: int, device_id: str = "") -> dict:
    """Single step that opens Gallery and selects `count` images."""
    return {
        "type": "ytcreate_add_images",
        "count": count,
        "label": f"Tambah {count} gambar ke project",
        "retry_max": 2,
        "device_id": device_id,
    }
