"""
Product preset API — MVP 0.4

Endpoints:
  GET    /products                    → list all saved products
  POST   /products/fetch              → scrape TikTok URL + AI analysis (no save)
  POST   /products/analyze-text       → AI analysis from pasted text (no save)
  POST   /products/analyze-images     → AI vision analysis from screenshots (no save)
  GET    /products/{id}               → get one saved product
  POST   /products                    → save a product preset
  PATCH  /products/{id}               → update a saved product
  POST   /products/{id}/refresh       → re-scrape and return diff (no auto-save)
  DELETE /products/{id}               → delete

Security: /fetch and /analyze-images validate domains / file types.
"""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_db
from app.models.product import SavedProduct
from app.services.product_scraper import (
    validate_url,
    normalize_url,
    fetch_product,
    download_image,
)
from app.services.product_duplicate import find_duplicate, conflict_message
from app.services.ai_generator import generate_product_analysis, analyze_images_with_vision
from app.core.config import settings

router = APIRouter(prefix="/products", tags=["products"])

UPLOAD_DIR = Path(__file__).parent.parent.parent / "uploads"
ALLOWED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
MAX_IMAGES = 5
MAX_IMAGE_BYTES = 8 * 1024 * 1024  # 8 MB per file
MIN_TEXT_CHARS = 20


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class FetchRequest(BaseModel):
    url: str
    manual_text: str = ""


class AnalyzeTextRequest(BaseModel):
    text: str
    product_url: str = ""  # optional, stored for reference


class SaveProductRequest(BaseModel):
    name: str
    url: str = ""          # empty for text/screenshot sources
    platform: str = "tiktok_shop"
    source_type: str = "url"
    product_id: str | None = None
    shop_name: str = ""
    price: str = ""
    description: str = ""
    image_filename: str | None = None
    image_url: str | None = None
    reference_image_path: str | None = None
    key_benefits: list[str] = []
    pain_points: list[str] = []
    desires: list[str] = []
    triggers: list[str] = []
    common_pain_points: list[str] = []
    buying_motivations: list[str] = []
    suggested_content_angles: list[str] = []
    target_audience: str = ""
    target_audience_options: list[str] = []
    default_video_objective: str = ""
    default_video_style: str = ""
    tiktok_product_name: str = ""


class CheckDuplicateRequest(BaseModel):
    url: str = ""
    product_id: str = ""
    name: str = ""
    shop_name: str = ""


class UpdateProductRequest(BaseModel):
    name: str | None = None
    url: str | None = None
    product_id: str | None = None
    shop_name: str | None = None
    price: str | None = None
    description: str | None = None
    image_filename: str | None = None
    image_url: str | None = None
    reference_image_path: str | None = None
    key_benefits: list[str] | None = None
    pain_points: list[str] | None = None
    desires: list[str] | None = None
    triggers: list[str] | None = None
    common_pain_points: list[str] | None = None
    buying_motivations: list[str] | None = None
    suggested_content_angles: list[str] | None = None
    target_audience: str | None = None
    target_audience_options: list[str] | None = None
    default_video_objective: str | None = None
    default_video_style: str | None = None
    tiktok_product_name: str | None = None
    source_type: str | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _require_openai() -> None:
    if not settings.openai_api_key:
        raise HTTPException(
            503,
            "OPENAI_API_KEY tidak dikonfigurasi. "
            "Isi backend/.env dengan API key OpenAI untuk AI analysis.",
        )


def _make_draft(
    scraped: dict,
    analysis: dict,
    canonical_url: str,
    source_type: str,
    source_images: list[str],
) -> dict:
    """
    Normalize scraped + analysis into a consistent ProductDraft shape.
    All analysis paths (URL, text, screenshot) produce this same dict.
    """
    return {
        "source_type": source_type,
        "product_url": canonical_url,
        "product_name": (
            scraped.get("title")
            or analysis.get("product_name")
            or analysis.get("tiktok_product_name")
            or ""
        ),
        "shop_name": scraped.get("shop_name") or analysis.get("shop_name") or "",
        "product_description": (
            scraped.get("description")
            or analysis.get("product_description")
            or ""
        ),
        "price": scraped.get("price") or analysis.get("price") or "",
        "key_benefits": analysis.get("key_benefits", []),
        "target_audience": analysis.get("target_audience", ""),
        "target_audience_options": analysis.get("target_audience_options", []),
        "common_pain_points": analysis.get("common_pain_points", []),
        "buying_motivations": analysis.get("buying_motivations", []),
        "suggested_content_angles": analysis.get("suggested_content_angles", []),
        "default_video_objective": analysis.get("default_video_objective", ""),
        "default_video_style": analysis.get("default_video_style", ""),
        "tiktok_product_name": (
            analysis.get("tiktok_product_name")
            or scraped.get("title")
            or ""
        ),
        "source_images": source_images,
        "confidence": analysis.get("confidence", 0.0),
        "warnings": analysis.get("warnings", []),
    }


async def _run_fetch_and_analyse(url: str, manual_text: str = "") -> dict:
    """Scrape a TikTok URL and run AI analysis. Returns combined dict with `draft` key."""
    scraped = await fetch_product(url)

    analysis: dict = {}
    ai_error = ""

    has_content = bool(scraped.get("title") or manual_text.strip())
    if has_content:
        _require_openai()
        try:
            analysis = generate_product_analysis(scraped, manual_text)
        except Exception as exc:
            ai_error = str(exc)

    image_filename: str | None = None
    if scraped.get("image_url") and not scraped["fetch_failed"]:
        image_filename = await download_image(scraped["image_url"])

    source_images = [image_filename] if image_filename else []
    draft = _make_draft(scraped, analysis, url, "url", source_images)

    return {
        "scraped": scraped,
        "analysis": analysis,
        "image_filename": image_filename,
        "fetch_failed": scraped.get("fetch_failed", False),
        "fetch_error": scraped.get("fetch_error", ""),
        "ai_error": ai_error,
        "draft": draft,
    }


# ── List ──────────────────────────────────────────────────────────────────────

@router.get("")
async def list_products(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SavedProduct).order_by(SavedProduct.created_at.desc())
    )
    return [p.to_dict() for p in result.scalars().all()]


# ── Fetch (scrape TikTok URL, no save) ───────────────────────────────────────

@router.post("/fetch")
async def fetch_product_data(req: FetchRequest, db: AsyncSession = Depends(get_db)):
    ok, err = validate_url(req.url)
    if not ok:
        raise HTTPException(422, err)

    canonical = normalize_url(req.url)

    existing_result = await db.execute(
        select(SavedProduct).where(SavedProduct.url == canonical)
    )
    existing = existing_result.scalar_one_or_none()

    result = await _run_fetch_and_analyse(canonical, req.manual_text)
    result["canonical_url"] = canonical
    result["existing_id"] = existing.id if existing else None

    return result


# ── Analyze from pasted text (no save) ───────────────────────────────────────

@router.post("/analyze-text")
async def analyze_text(req: AnalyzeTextRequest):
    """
    Run AI product analysis on user-pasted text.
    Does not scrape any URL. Returns a ProductDraft.
    """
    text = req.text.strip()
    if len(text) < MIN_TEXT_CHARS:
        raise HTTPException(
            422,
            f"Teks terlalu pendek (minimum {MIN_TEXT_CHARS} aksara). "
            "Salin lebih banyak maklumat produk dari TikTok Shop.",
        )
    if len(text.split()) < 4:
        raise HTTPException(422, "Teks tidak mengandungi maklumat yang mencukupi.")

    _require_openai()

    try:
        analysis = generate_product_analysis(
            product={"title": "", "description": "", "price": "", "shop_name": ""},
            manual_text=text,
        )
    except Exception as exc:
        raise HTTPException(500, f"AI analysis gagal: {exc}")

    draft = _make_draft(
        scraped={},
        analysis=analysis,
        canonical_url=req.product_url,
        source_type="text",
        source_images=[],
    )
    return draft


# ── Analyze from screenshots (no save) ───────────────────────────────────────

@router.post("/analyze-images")
async def analyze_images(
    images: list[UploadFile] = File(...),
    product_url: str = Form(default=""),
    notes: str = Form(default=""),
):
    """
    Run AI vision analysis on uploaded product screenshots.
    Saves images to uploads/ for display and later reference-image selection.
    Returns a ProductDraft.
    """
    if not images:
        raise HTTPException(422, "Sila upload sekurang-kurangnya satu gambar.")
    if len(images) > MAX_IMAGES:
        raise HTTPException(422, f"Maksimum {MAX_IMAGES} gambar sahaja.")

    _require_openai()
    UPLOAD_DIR.mkdir(exist_ok=True)

    saved_paths: list[str] = []
    saved_filenames: list[str] = []

    for upload in images:
        # Validate file type
        filename = upload.filename or ""
        suffix = Path(filename).suffix.lower()
        if suffix not in ALLOWED_IMAGE_SUFFIXES:
            raise HTTPException(
                422,
                f"Format fail '{suffix}' tidak disokong. "
                "Gunakan JPG, PNG, atau WEBP.",
            )

        content = await upload.read()
        if len(content) > MAX_IMAGE_BYTES:
            raise HTTPException(
                422,
                f"Saiz fail terlalu besar (maksimum {MAX_IMAGE_BYTES // (1024*1024)} MB).",
            )

        out_filename = f"{uuid.uuid4().hex}{suffix}"
        out_path = UPLOAD_DIR / out_filename
        out_path.write_bytes(content)
        saved_paths.append(str(out_path))
        saved_filenames.append(out_filename)

    try:
        vision_result = analyze_images_with_vision(
            image_paths=saved_paths,
            notes=notes,
            product_url=product_url,
        )
    except Exception as exc:
        raise HTTPException(500, f"Vision analysis gagal: {exc}")

    if not vision_result.get("vision_available", True) and vision_result.get("error"):
        # Vision failed but images were saved — return fallback draft with saved images
        draft = _make_draft(
            scraped={},
            analysis=vision_result,
            canonical_url=product_url,
            source_type="screenshot",
            source_images=saved_filenames,
        )
        draft["vision_error"] = vision_result.get("error", "")
        return draft

    draft = _make_draft(
        scraped={
            "title": vision_result.get("product_name", ""),
            "shop_name": vision_result.get("shop_name", ""),
            "description": vision_result.get("product_description", ""),
            "price": vision_result.get("price", ""),
        },
        analysis=vision_result,
        canonical_url=product_url,
        source_type="screenshot",
        source_images=saved_filenames,
    )
    return draft


# ── Search ───────────────────────────────────────────────────────────────────

@router.get("/search")
async def search_products(q: str = "", db: AsyncSession = Depends(get_db)):
    """Filter saved products by name (case-insensitive substring match)."""
    result = await db.execute(
        select(SavedProduct).order_by(SavedProduct.updated_at.desc())
    )
    products = result.scalars().all()
    if q.strip():
        needle = q.strip().lower()
        products = [p for p in products if needle in p.name.lower() or needle in (p.shop_name or "").lower()]
    return [p.to_dict() for p in products]


# ── Duplicate check ───────────────────────────────────────────────────────────

@router.post("/check-duplicate")
async def check_duplicate(req: CheckDuplicateRequest, db: AsyncSession = Depends(get_db)):
    """
    Check whether a product already exists without saving.
    Returns {exists, matched_by, product}.
    """
    dup = await find_duplicate(
        db,
        url=req.url,
        product_id=req.product_id or None,
        name=req.name,
        shop_name=req.shop_name,
    )
    return {
        "exists": dup.existing is not None,
        "matched_by": dup.matched_by,
        "product": dup.existing.to_dict() if dup.existing else None,
    }


# ── Get one ───────────────────────────────────────────────────────────────────

@router.get("/{product_id}")
async def get_product(product_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SavedProduct).where(SavedProduct.id == product_id)
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Produk tidak dijumpai.")
    return p.to_dict()


# ── Save preset ───────────────────────────────────────────────────────────────

@router.post("")
async def save_product(req: SaveProductRequest, db: AsyncSession = Depends(get_db)):
    """Save a product preset. Returns 409 with structured detail on duplicate."""
    canonical = normalize_url(req.url) if req.url.startswith("http") else req.url
    if not canonical:
        canonical = f"local://{uuid.uuid4().hex}"

    dup = await find_duplicate(
        db,
        url=req.url,
        product_id=req.product_id,
        name=req.name,
        shop_name=req.shop_name,
    )
    if dup.existing:
        raise HTTPException(
            409,
            detail={
                "message": conflict_message(dup.matched_by, dup.existing.name),
                "existing_product_id": dup.existing.id,
                "existing_product_name": dup.existing.name,
                "matched_by": dup.matched_by,
                "existing_product": dup.existing.to_dict(),
            },
        )

    product = SavedProduct(
        name=req.name,
        url=canonical,
        platform=req.platform,
        source_type=req.source_type,
        product_id=req.product_id,
        shop_name=req.shop_name,
        price=req.price,
        description=req.description,
        image_filename=req.image_filename,
        image_url=req.image_url,
        reference_image_path=req.reference_image_path,
        key_benefits=json.dumps(req.key_benefits, ensure_ascii=False),
        pain_points=json.dumps(req.pain_points, ensure_ascii=False),
        desires=json.dumps(req.desires, ensure_ascii=False),
        triggers=json.dumps(req.triggers, ensure_ascii=False),
        common_pain_points=json.dumps(req.common_pain_points, ensure_ascii=False),
        buying_motivations=json.dumps(req.buying_motivations, ensure_ascii=False),
        suggested_content_angles=json.dumps(req.suggested_content_angles, ensure_ascii=False),
        target_audience=req.target_audience,
        target_audience_options=json.dumps(req.target_audience_options, ensure_ascii=False),
        default_video_objective=req.default_video_objective,
        default_video_style=req.default_video_style,
        tiktok_product_name=req.tiktok_product_name,
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product.to_dict()


# ── Update preset ─────────────────────────────────────────────────────────────

@router.patch("/{product_id}")
async def update_product(
    product_id: int,
    req: UpdateProductRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SavedProduct).where(SavedProduct.id == product_id)
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Produk tidak dijumpai.")

    # Check for conflicts when identity fields change
    if req.name is not None or req.shop_name is not None or req.url is not None or req.product_id is not None:
        effective_url = req.url if req.url is not None else (p.url or "")
        effective_pid = req.product_id if req.product_id is not None else (p.product_id or None)
        effective_name = req.name if req.name is not None else p.name
        effective_shop = req.shop_name if req.shop_name is not None else (p.shop_name or "")
        dup = await find_duplicate(
            db,
            url=effective_url,
            product_id=effective_pid,
            name=effective_name,
            shop_name=effective_shop,
            exclude_id=product_id,
        )
        if dup.existing:
            raise HTTPException(
                409,
                detail={
                    "message": conflict_message(dup.matched_by, dup.existing.name),
                    "existing_product_id": dup.existing.id,
                    "existing_product_name": dup.existing.name,
                    "matched_by": dup.matched_by,
                    "existing_product": dup.existing.to_dict(),
                },
            )

    for field, value in {
        "name": req.name,
        "url": req.url,
        "product_id": req.product_id,
        "shop_name": req.shop_name,
        "price": req.price,
        "description": req.description,
        "image_filename": req.image_filename,
        "image_url": req.image_url,
        "reference_image_path": req.reference_image_path,
        "target_audience": req.target_audience,
        "default_video_objective": req.default_video_objective,
        "default_video_style": req.default_video_style,
        "tiktok_product_name": req.tiktok_product_name,
        "source_type": req.source_type,
    }.items():
        if value is not None:
            setattr(p, field, value)

    for field, value in {
        "key_benefits": req.key_benefits,
        "pain_points": req.pain_points,
        "desires": req.desires,
        "triggers": req.triggers,
        "common_pain_points": req.common_pain_points,
        "buying_motivations": req.buying_motivations,
        "suggested_content_angles": req.suggested_content_angles,
        "target_audience_options": req.target_audience_options,
    }.items():
        if value is not None:
            setattr(p, field, json.dumps(value, ensure_ascii=False))

    p.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(p)
    return p.to_dict()


# ── Refresh (re-scrape, no auto-save) ────────────────────────────────────────

@router.post("/{product_id}/refresh")
async def refresh_product(product_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SavedProduct).where(SavedProduct.id == product_id)
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Produk tidak dijumpai.")

    # Only TikTok URLs can be refreshed via scraping
    if not p.url.startswith("http"):
        raise HTTPException(
            422,
            "Produk ini disimpan dari teks/screenshot — tiada URL untuk di-refresh. "
            "Gunakan 'Analyze Text' semula jika anda ada maklumat terbaru.",
        )

    fresh = await _run_fetch_and_analyse(p.url)
    saved = p.to_dict()

    diff: dict[str, dict] = {}
    scraped = fresh.get("scraped", {})
    for saved_field, scraped_field in [
        ("name", "title"),
        ("shop_name", "shop_name"),
        ("description", "description"),
        ("price", "price"),
    ]:
        old_val = saved.get(saved_field, "")
        new_val = scraped.get(scraped_field, "")
        if old_val != new_val and new_val:
            diff[saved_field] = {"old": old_val, "new": new_val}

    return {**fresh, "saved": saved, "diff": diff, "has_changes": bool(diff)}


# ── Delete ────────────────────────────────────────────────────────────────────

@router.delete("/{product_id}")
async def delete_product(product_id: int, db: AsyncSession = Depends(get_db)):
    await db.execute(delete(SavedProduct).where(SavedProduct.id == product_id))
    await db.commit()
    return {"status": "deleted"}
