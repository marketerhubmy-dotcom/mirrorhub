"""
Prompt builders for Content Pipeline — MVP 0.6.

All prompts receive a ProductContentContext dict and generate content that is
specific to the selected product, avatar, angle, and video type.
Pure functions — no side effects, no API calls.
"""


def _benefits_block(benefits: list[str]) -> str:
    return "\n".join(f"  - {b}" for b in benefits) if benefits else "  (tiada)"


def _list_block(items: list[str]) -> str:
    return "\n".join(f"  - {i}" for i in items) if items else "  (tiada)"


def build_brief_prompt(ctx: dict) -> str:
    """Generate hook + story + cta from product context."""
    return f"""Kau adalah content strategist pakar TikTok Malaysia.

PRODUK:
Nama: {ctx.get('product_name', ctx.get('product', ''))}
Deskripsi: {ctx.get('product_description', '')}
Manfaat Utama:
{_benefits_block(ctx.get('key_benefits', []))}
Target Audiens: {ctx.get('target_audience', ctx.get('audience', ''))}
Titik Kesakitan Pelanggan:
{_list_block(ctx.get('pain_points', []))}
Motivasi Membeli:
{_list_block(ctx.get('buying_motivations', []))}

CONTENT BRIEF:
Jenis Video: {ctx.get('video_type', '')}
Content Angle: {ctx.get('content_angle', ctx.get('topic', ''))}
Gaya Visual: {ctx.get('visual_style', '')}
Avatar/Watak: {ctx.get('avatar', '')}
Arahan Khas: {ctx.get('custom_instructions', '')}

Jana dalam format JSON dengan 3 key:
- hook: Ayat pembuka yang menarik perhatian dalam 3 saat (max 15 patah perkataan). \
Mestilah berkaitan terus dengan produk atau masalah yang diselesaikannya.
- story: Isi cerita — masalah, penyelesaian, manfaat produk (2-3 ayat). \
Sebutkan nama produk sekurang-kurangnya sekali.
- cta: Call-to-action yang jelas (max 8 patah perkataan).

Bahasa Malaysia natural, boleh mix English. Spesifik kepada produk ini, BUKAN generik."""


def build_video_prompt_prompt(ctx: dict) -> str:
    """Generate YouTube Create / Sora video prompt from product + avatar context."""
    avatar_desc = ctx.get('avatar', '')
    product_name = ctx.get('product_name', ctx.get('product', ''))
    dialogue = ctx.get('custom_instructions', '')
    has_second_image = bool(ctx.get('avatar_reference_image', ''))

    return f"""You are an expert AI video prompt writer for YouTube Create (Google Veo).

PRODUCT:
Name: {product_name}
Description: {ctx.get('product_description', '')}
Key Benefits: {', '.join(ctx.get('key_benefits', [])) or 'N/A'}

VIDEO BRIEF:
Hook: {ctx.get('hook', '')}
Story: {ctx.get('story', '')}
CTA: {ctx.get('cta', '')}
Video Type: {ctx.get('video_type', '')}
Content Angle: {ctx.get('content_angle', ctx.get('topic', ''))}
Visual Style: {ctx.get('visual_style', '')}
Duration: {ctx.get('duration', '8s')}

CHARACTER / AVATAR:
{avatar_desc if avatar_desc else ('The person shown in the second reference image.' if has_second_image else 'No specific character — focus on product.')}

DIALOGUE / SPECIAL INSTRUCTIONS:
{dialogue if dialogue else '(none — no spoken dialogue, silent/VO-free product footage)'}

REFERENCE IMAGE(S):
{"Two reference images were uploaded: the FIRST shows the actual product packaging — use it as the visual source for product appearance, do NOT invent a different product design. The SECOND shows the avatar/character — match this person's face, look and identity for the CHARACTER in the video." if has_second_image else "The uploaded reference image shows the actual product packaging. Use it as the visual source for the product appearance. Do NOT invent a different product design."}

REQUIREMENTS — include ALL in the prompt:
1. Subject and avatar (based on CHARACTER above)
2. Location / setting (fits product and audience)
3. Avatar appearance and attire (if character present)
4. Product appearance and placement (must match reference image)
5. Camera movement (e.g. slow push in, handheld, close-up to wide)
6. Character action (what they are doing with the product)
7. If DIALOGUE is provided above, the avatar speaks that exact line on camera (spoken dialogue, lip-synced) — state this explicitly in the prompt
8. Emotion and expression
9. Lighting (natural, soft, studio, golden hour, etc.)
10. Video style (realistic, cinematic, UGC, etc.)
11. Vertical format, {ctx.get('duration', '8s')} duration
12. NO random text overlays on screen

Output: single video prompt in English, max 120 words, no labels or explanations."""


def build_cover_hook_prompt(ctx: dict) -> str:
    """Generate a short TikTok cover hook (≤3 lines, high impact)."""
    product_name = ctx.get('product_name', ctx.get('product', ''))
    return f"""Kau adalah pakar TikTok cover text Malaysia.

PRODUK: {product_name}
CONTENT ANGLE: {ctx.get('content_angle', ctx.get('topic', ''))}
HOOK VIDEO: {ctx.get('hook', '')}
Titik Kesakitan:
{_list_block(ctx.get('pain_points', []))}

Jana SATU cover hook untuk TikTok video dengan format:
- Maksimum 3 baris pendek
- Setiap baris: 2-5 perkataan
- Huruf besar (UPPERCASE)
- Tiada hashtag, tiada emoji
- Kuat — buat orang berhenti scroll
- Berkaitan dengan masalah pelanggan atau manfaat produk
- Tiada dakwaan melampau yang tidak boleh dibuktikan

Contoh format:
KULIT KUSAM HARI-HARI?
RUPANYA ADA
SEBAB TERSEMBUNYI...

Output: teks cover hook sahaja, tiada label, tiada penjelasan."""


def build_caption_prompt(ctx: dict) -> str:
    """Generate TikTok caption in Bahasa Malaysia from product + content context."""
    product_name = ctx.get('product_name', ctx.get('product', ''))
    return f"""Kau adalah TikTok copywriter Malaysia.

PRODUK: {product_name}
Deskripsi: {ctx.get('product_description', '')}
Manfaat: {', '.join(ctx.get('key_benefits', [])) or 'N/A'}
Target Audiens: {ctx.get('target_audience', ctx.get('audience', ''))}
Content Angle: {ctx.get('content_angle', ctx.get('topic', ''))}

VIDEO BRIEF:
Hook: {ctx.get('hook', '')}
Story: {ctx.get('story', '')}
CTA: {ctx.get('cta', '')}
Jenis Video: {ctx.get('video_type', '')}
Arahan Khas: {ctx.get('custom_instructions', '')}

Jana caption TikTok:
- 2-3 ayat maksimum
- Bahasa Malaysia natural, boleh mix English sedikit
- Ada hook di awal
- Sebutkan manfaat produk secara ringkas
- Sertakan emoji yang relevan (jangan berlebihan)
- Akhir dengan CTA ringkas
- Sesuai untuk Malaysia audience
- JANGAN tulis hashtag — ia akan dijana berasingan

Output: caption teks sahaja, tiada label."""


def build_hashtags_prompt(ctx: dict) -> str:
    """Generate 3–5 focused, product-relevant TikTok hashtags."""
    product_name = ctx.get('product_name', ctx.get('product', ''))
    return f"""Berdasarkan konten berikut, syor hashtag TikTok Malaysia yang berkesan.

Produk: {product_name}
Audiens: {ctx.get('target_audience', ctx.get('audience', ''))}
Content Angle: {ctx.get('content_angle', ctx.get('topic', ''))}
Jenis Video: {ctx.get('video_type', '')}
Gaya Visual: {ctx.get('visual_style', '')}

Jana dalam format JSON: {{ "hashtags": ["#tag1", "#tag2", ...] }}

Keperluan KETAT:
- 3 hingga 5 hashtag sahaja (bukan 8-12)
- Relevan kepada produk, audiens, dan content angle
- Mix: product-specific (1-2), niche/problem (1-2), Malaysia (0-1)
- TIADA hashtag trending yang tidak berkaitan dengan produk
- Semua bermula dengan #
- Bahasa Malaysia + English"""
