import base64
import json
import mimetypes
from pathlib import Path

from openai import OpenAI
from app.core.config import settings


def _client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key)


def generate_avatar_questions(product: dict) -> dict:
    """Generate product-specific pain points, desires and triggers using AI."""
    product_text = (
        f"Nama: {product.get('title', '')}\n"
        f"Harga: {product.get('price', '')}\n"
        f"Info: {product.get('description', '')[:400]}"
    )

    prompt = f"""Berdasarkan produk berikut, jana soalan avatar yang SPESIFIK untuk produk ini bagi strategi konten TikTok Malaysia.

PRODUK:
{product_text}

Jana dalam format JSON dengan 3 key:
- pain_points: list 6-8 masalah/frustrasi yang avatar hadapi, berkaitan terus dengan produk ini
- desires: list 5-7 keinginan/goal avatar yang produk ini boleh bantu capai
- triggers: list 5-6 faktor yang akan buat mereka terus beli produk ini

Bahasa Malaysia yang natural. Spesifik untuk produk ini, bukan generik."""

    resp = _client().chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=600,
        temperature=0.7,
        response_format={"type": "json_object"},
    )

    try:
        return json.loads(resp.choices[0].message.content)
    except Exception:
        return {"pain_points": [], "desires": [], "triggers": []}


def generate_video_script(topic: str, language: str = "ms") -> str:
    """Simple script generation (legacy — for AI API mode)."""
    prompt = (
        f"Jana script video TikTok 30-45 saat untuk promosi: {topic}. "
        "Bahasa Malaysia natural. Ada hook, faedah produk, CTA. Teks sahaja."
    )
    resp = _client().chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300,
        temperature=0.8,
    )
    return resp.choices[0].message.content.strip()


def generate_product_analysis(product: dict, manual_text: str = "") -> dict:
    """
    Analyse a product and return structured data for pipeline pre-fill.

    Uses only information present in `product` (from scraper) or `manual_text`
    (user-pasted). Never invents medical claims or certifications not in the source.

    Returns:
        target_audience           str   (first / primary option)
        target_audience_options   list[str]  (3-5 choices)
        common_pain_points        list[str]
        buying_motivations        list[str]
        suggested_content_angles  list[str]
        default_video_objective   str
        default_video_style       str
        tiktok_product_name       str
        key_benefits              list[str]
        confidence                float  (0.0–1.0)
        warnings                  list[str]
    """
    title = product.get("title", "").strip()
    description = (product.get("description", "") or "").strip()
    price = (product.get("price", "") or "").strip()
    shop_name = (product.get("shop_name", "") or "").strip()

    source_text = manual_text.strip() if manual_text else ""
    product_block = (
        f"Nama Produk: {title}\n"
        f"Kedai: {shop_name}\n"
        f"Harga: {price}\n"
        f"Deskripsi: {description[:600]}"
    )
    if source_text:
        product_block += f"\n\nMaklumat tambahan (dari pengguna):\n{source_text[:1000]}"

    has_good_data = bool(title or source_text)

    prompt = f"""Kau pakar strategi konten TikTok Malaysia. Berdasarkan maklumat produk ini sahaja, jana analisis untuk pipeline konten.

PRODUK:
{product_block}

Jana dalam format JSON dengan key TEPAT berikut:
- target_audience: string ringkas — pilihan pertama (contoh: "Ibu bapa dengan anak sekolah rendah")
- target_audience_options: list 3-5 pilihan audience yang berbeza (dari spesifik ke lebih umum)
- common_pain_points: list 4-6 masalah pelanggan berkaitan produk ini (Bahasa Malaysia)
- buying_motivations: list 3-5 sebab pelanggan beli produk ini
- suggested_content_angles: list 5-7 angle video TikTok yang sesuai (pendek, deskriptif)
- default_video_objective: string (contoh: "Drive klik ke link produk TikTok Shop")
- default_video_style: string (contoh: "lifestyle natural, close-up produk, pencahayaan terang")
- tiktok_product_name: string — nama tepat untuk dicari dalam TikTok Shop (pendek, tepat)
- key_benefits: list 3-5 manfaat utama produk berdasarkan maklumat di atas sahaja
- confidence: float 0.0 hingga 1.0 (seberapa yakin analisis ini, berdasarkan kualiti maklumat yang diberikan)
- warnings: list string — maklumat yang tidak jelas atau tidak disokong oleh data (kosong jika tiada)

PERATURAN PENTING:
- Gunakan HANYA maklumat yang ada dalam produk di atas.
- Jangan cipta klaim perubatan, sijil, atau manfaat yang tidak disebut.
- Jangan reka ulasan atau testimoni.
- Jika maklumat terhad, nilai confidence rendah dan sertakan warnings."""

    resp = _client().chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=900,
        temperature=0.6,
        response_format={"type": "json_object"},
    )

    try:
        data = json.loads(resp.choices[0].message.content)
    except Exception:
        data = {}

    # Ensure target_audience_options contains at least the primary audience
    options = data.get("target_audience_options") or []
    primary = data.get("target_audience", "")
    if primary and primary not in options:
        options = [primary] + options
    if not options and primary:
        options = [primary]

    return {
        "target_audience": primary or (options[0] if options else ""),
        "target_audience_options": options,
        "common_pain_points": data.get("common_pain_points", []),
        "buying_motivations": data.get("buying_motivations", []),
        "suggested_content_angles": data.get("suggested_content_angles", []),
        "default_video_objective": data.get("default_video_objective", ""),
        "default_video_style": data.get("default_video_style", ""),
        "tiktok_product_name": data.get("tiktok_product_name", title),
        "key_benefits": data.get("key_benefits", []),
        "confidence": float(data.get("confidence", 0.5 if has_good_data else 0.2)),
        "warnings": data.get("warnings", []),
    }


def analyze_images_with_vision(
    image_paths: list[str],
    notes: str = "",
    product_url: str = "",
) -> dict:
    """
    Analyse product screenshots using GPT-4o-mini vision.

    image_paths: list of absolute paths to saved image files in uploads/
    notes: optional user-provided text context
    product_url: optional product URL (for reference, not fetched)

    Returns a ProductDraft-compatible dict with both extracted facts and AI analysis.
    Never invents information not visible in the screenshots.
    """
    if not image_paths:
        return _empty_vision_draft("Tiada gambar yang diberikan.")

    # Build vision message content
    content: list[dict] = []

    context_parts = []
    if product_url:
        context_parts.append(f"URL Produk: {product_url}")
    if notes.strip():
        context_parts.append(f"Nota tambahan dari pengguna:\n{notes.strip()[:500]}")

    context_block = "\n".join(context_parts)

    prompt_text = f"""Kau pakar analisis produk TikTok Malaysia. Lihat screenshot produk TikTok Shop yang dihantar.

{context_block}

Ekstrak SEMUA maklumat yang KELIHATAN dalam screenshot dan jana analisis konten.

Jana dalam format JSON dengan key berikut:
- product_name: string — nama produk tepat seperti yang tertulis dalam screenshot
- shop_name: string — nama kedai/seller jika kelihatan (kosong jika tidak nampak)
- price: string — harga seperti yang terpapar (contoh: "RM89.90"), kosong jika tidak kelihatan
- product_description: string — deskripsi atau info produk yang kelihatan dalam screenshot
- key_benefits: list string — manfaat atau ciri yang KELIHATAN dalam screenshot sahaja
- target_audience: string — audience utama berdasarkan produk ini
- target_audience_options: list 3-5 pilihan audience yang berbeza
- common_pain_points: list 4-6 masalah pelanggan yang berkaitan
- buying_motivations: list 3-5 sebab pelanggan beli
- suggested_content_angles: list 5-7 angle video TikTok yang sesuai
- default_video_objective: string
- default_video_style: string
- tiktok_product_name: string — nama untuk dicari dalam TikTok Shop
- confidence: float 0.0 hingga 1.0 (bergantung pada kejelasan screenshot)
- warnings: list string — maklumat yang tidak jelas atau tidak dapat disahkan dari screenshot

PERATURAN PENTING:
- Hanya ekstrak maklumat yang KELIHATAN dalam screenshot.
- Jangan reka atau tampal maklumat yang tidak ada.
- Jangan cipta klaim perubatan atau sijil yang tidak ditunjukkan.
- Jika screenshot kabur atau terpotong, nyatakan dalam warnings dan turunkan confidence."""

    content.append({"type": "text", "text": prompt_text})

    # Add each image
    for path in image_paths[:5]:  # hard cap at 5
        try:
            img_bytes = Path(path).read_bytes()
        except Exception:
            continue
        # Detect MIME type
        suffix = Path(path).suffix.lower()
        mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
        mime = mime_map.get(suffix, "image/jpeg")
        b64 = base64.b64encode(img_bytes).decode()
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:{mime};base64,{b64}",
                "detail": "auto",
            },
        })

    if len(content) == 1:
        # Only the text prompt, no images loaded successfully
        return _empty_vision_draft("Gagal membaca fail gambar.")

    try:
        resp = _client().chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": content}],
            max_tokens=900,
            temperature=0.4,
            response_format={"type": "json_object"},
        )
        data = json.loads(resp.choices[0].message.content)
    except Exception as exc:
        # If vision is not available (e.g. API restriction), return clear message
        return _empty_vision_draft(f"Vision analysis gagal: {exc}")

    options = data.get("target_audience_options") or []
    primary = data.get("target_audience", "")
    if primary and primary not in options:
        options = [primary] + options

    return {
        "product_name": data.get("product_name", ""),
        "shop_name": data.get("shop_name", ""),
        "price": data.get("price", ""),
        "product_description": data.get("product_description", ""),
        "key_benefits": data.get("key_benefits", []),
        "target_audience": primary or (options[0] if options else ""),
        "target_audience_options": options,
        "common_pain_points": data.get("common_pain_points", []),
        "buying_motivations": data.get("buying_motivations", []),
        "suggested_content_angles": data.get("suggested_content_angles", []),
        "default_video_objective": data.get("default_video_objective", ""),
        "default_video_style": data.get("default_video_style", ""),
        "tiktok_product_name": data.get("tiktok_product_name", ""),
        "confidence": float(data.get("confidence", 0.7)),
        "warnings": data.get("warnings", []),
        "vision_available": True,
        "error": "",
    }


def _empty_vision_draft(reason: str) -> dict:
    return {
        "product_name": "", "shop_name": "", "price": "", "product_description": "",
        "key_benefits": [], "target_audience": "", "target_audience_options": [],
        "common_pain_points": [], "buying_motivations": [], "suggested_content_angles": [],
        "default_video_objective": "", "default_video_style": "", "tiktok_product_name": "",
        "confidence": 0.0, "warnings": [reason],
        "vision_available": False, "error": reason,
    }


def generate_scripts_for_angles(
    product: dict,
    avatar: dict,
    angles: list[str],
    custom_format: str | None = None,
) -> dict[str, str]:
    """Generate one prompt/script per angle.

    If custom_format is provided, AI fills in that template for each angle
    (video creation prompt mode). Otherwise, generates a short VO script.
    """
    client = _client()
    scripts: dict[str, str] = {}

    avatar_text = (
        f"Jantina: {avatar.get('gender', 'Wanita')}\n"
        f"Umur: {avatar.get('age', '25-34')}\n"
        f"Pain points: {', '.join(avatar.get('pain_points', []))}\n"
        f"Keinginan: {', '.join(avatar.get('desires', []))}\n"
        f"Trigger beli: {', '.join(avatar.get('triggers', []))}"
    )

    product_text = (
        f"Nama: {product.get('title', '')}\n"
        f"Harga: {product.get('price', '')}\n"
        f"Info: {product.get('description', '')[:300]}"
    )

    for angle in angles:
        if custom_format:
            prompt = f"""Kau pakar video prompt untuk AI video generator.

PRODUK:
{product_text}

TARGET AVATAR:
{avatar_text}

ANGLE VIDEO: {angle}

Gunakan format template prompt di bawah. Isi / gantikan semua placeholder (contoh: [SCENE], [CAMERA MOVEMENT], [MODEL], [ACTION] dll) dengan yang sesuai untuk angle "{angle}" dan produk di atas. Kekalkan struktur format asal — hanya ganti placeholders sahaja.

FORMAT TEMPLATE:
{custom_format}

Output: Prompt yang dah diisi sahaja. Tiada penjelasan tambahan."""
            max_tok = 400
        else:
            prompt = f"""Kau copywriter TikTok Malaysia. Jana script video 8 saat untuk angle "{angle}".

PRODUK:
{product_text}

TARGET AVATAR:
{avatar_text}

Keperluan:
- Maksimum 25 patah perkataan (8 saat bila dibaca)
- Bahasa Malaysia natural, boleh mix English
- Connect dengan pain point / keinginan avatar

Output: Script teks sahaja. Tiada label, tiada penjelasan."""
            max_tok = 80

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tok,
            temperature=0.8,
        )
        scripts[angle] = resp.choices[0].message.content.strip()

    return scripts
