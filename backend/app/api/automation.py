import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_db
from app.devices.registry import get_device
from app.services import ai_generator, automation_runner, product_scraper

router = APIRouter(prefix="/automation", tags=["automation"])

from app.utils.paths import UPLOAD_DIR
UPLOAD_DIR.mkdir(exist_ok=True)


# ── Request / Response models ─────────────────────────────────────────────────

class FetchProductRequest(BaseModel):
    url: str

class GenerateScriptsRequest(BaseModel):
    product: dict
    avatar: dict
    angles: list[str]
    custom_format: str | None = None  # User's prompt template — AI fills in placeholders

class GenerateScriptRequest(BaseModel):
    topic: str
    language: str = "ms"

class GenerateScriptResponse(BaseModel):
    script: str

class RunRequest(BaseModel):
    device_id: str
    script: str
    image_filename: str
    post_type: str
    schedule_time: str | None = None
    use_chatgpt_app: bool = False
    chatgpt_topic: str = ""
    chatgpt_wait: int = 30
    custom_prompt: str | None = None

class RunStatus(BaseModel):
    running: bool
    logs: list[dict]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/fetch-product")
async def fetch_product(req: FetchProductRequest):
    """Fetch product info, download image, and generate avatar questions."""
    try:
        info = await product_scraper.fetch_product(req.url)

        image_filename = None
        if info.get("image_url"):
            image_filename = await product_scraper.download_image(info["image_url"])

        # Generate product-specific avatar questions
        avatar_qs = ai_generator.generate_avatar_questions(info)

        return {**info, "image_filename": image_filename, "avatar_questions": avatar_qs}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Gagal fetch produk: {e}")


@router.post("/generate-scripts")
def generate_scripts(req: GenerateScriptsRequest):
    """Generate scripts for multiple angles based on product + avatar."""
    try:
        scripts = ai_generator.generate_scripts_for_angles(
            product=req.product,
            avatar=req.avatar,
            angles=req.angles,
            custom_format=req.custom_format,
        )
        return {"scripts": scripts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate-script", response_model=GenerateScriptResponse)
def generate_script(req: GenerateScriptRequest):
    try:
        return GenerateScriptResponse(
            script=ai_generator.generate_video_script(req.topic, req.language)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload-image")
async def upload_image(file: UploadFile = File(...)):
    ext = Path(file.filename or "image.jpg").suffix or ".jpg"
    filename = f"{uuid.uuid4().hex}{ext}"
    dest = UPLOAD_DIR / filename
    dest.write_bytes(await file.read())
    return {"filename": filename}


@router.post("/run")
async def run_automation(req: RunRequest, db: AsyncSession = Depends(get_db)):
    device = await get_device(db, req.device_id)
    if not device or not device.adb_address:
        raise HTTPException(status_code=404, detail="Device tidak jumpa")

    image_path = UPLOAD_DIR / req.image_filename
    if not image_path.exists():
        raise HTTPException(status_code=400, detail="Image tidak jumpa")

    steps: list[dict] = []
    if req.use_chatgpt_app:
        prompt = req.custom_prompt or req.chatgpt_topic
        steps += automation_runner.build_chatgpt_steps(prompt, req.chatgpt_wait)

    steps += automation_runner.build_workflow(
        script=req.script,
        image_local_path=str(image_path),
        post_type=req.post_type,
        schedule_time=req.schedule_time,
        use_clipboard=req.use_chatgpt_app,
    )

    await automation_runner.start(req.device_id, device.adb_address, steps)
    return {"status": "started", "total_steps": len(steps)}


@router.delete("/stop/{device_id}")
def stop_automation(device_id: str):
    automation_runner.stop(device_id)
    return {"status": "stopped"}


@router.get("/status/{device_id}", response_model=RunStatus)
def get_status(device_id: str):
    runner = automation_runner.get_runner(device_id)
    if not runner:
        return RunStatus(running=False, logs=[])
    return RunStatus(running=runner.running, logs=runner.logs)
