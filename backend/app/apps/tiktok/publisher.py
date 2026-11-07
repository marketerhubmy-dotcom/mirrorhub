"""
Caption, product, and publish step builders for the TikTok Publisher plugin.

Builds the post-upload half of the workflow:
  caption entry → hashtags → product attachment → pre-publish check → publish → verify
"""
from .caption import build_caption
from .product import product_manager, TikTokProduct


def build_caption_steps(
    caption: str,
    hashtags: list[str],
    variables: dict[str, str] | None,
    device_id: str = "",
) -> list[dict]:
    """
    Build steps to enter caption + hashtags into TikTok's edit screen.

    The final assembled caption string is embedded into the step dict so
    the execution handler can read it directly without re-building it.
    """
    _d = {"device_id": device_id}
    full_caption = build_caption(caption, hashtags, variables)

    return [
        {
            "type": "tiktok_insert_caption",
            "label": "Masukkan caption",
            "caption": full_caption,
            "retry_max": 2,
            **_d,
        }
    ]


def build_product_steps(product: TikTokProduct, device_id: str = "") -> list[dict]:
    """
    Build steps to attach a TikTok Shop product.

    Steps:
      1. Open product selector
      2. Search by product.search_term
      3. Tap the first result (Vision Engine verifies correct name)
      4. Confirm attachment
    """
    _d = {"device_id": device_id}

    return [
        {
            "type": "tiktok_open_product_selector",
            "label": "Buka product selector",
            "retry_max": 2,
            **_d,
        },
        {
            "type": "tiktok_search_product",
            "label": f"Cari produk: {product.name}",
            "search_term": product.search_term,
            "product_name": product.name,
            "product_id": product.id,
            "retry_max": 3,
            **_d,
        },
        {
            "type": "tiktok_attach_product",
            "label": f"Attach produk: {product.name}",
            "product_name": product.name,
            "retry_max": 2,
            **_d,
        },
    ]


def build_publish_steps(
    post_type: str = "post_now",
    first_comment: str = "",
    device_id: str = "",
) -> list[dict]:
    """
    Build the final publish sequence:
      1. Pre-publish validation check (Vision Engine)
      2. Tap Publish / Save Draft
      3. Verify success screen
      4. Optionally post a first comment
    """
    _d = {"device_id": device_id}
    steps: list[dict] = []

    steps.append({
        "type": "tiktok_pre_publish_check",
        "label": "Semak sebelum publish",
        "retry_max": 1,
        **_d,
    })

    steps.append({
        "type": "tiktok_publish",
        "label": "Publish ke TikTok",
        "post_type": post_type,
        "retry_max": 2,
        **_d,
    })

    steps.append({
        "type": "tiktok_verify_success",
        "label": "Verify publish berjaya",
        "retry_max": 2,
        **_d,
    })

    if first_comment and post_type == "post_now":
        steps.append({
            "type": "tiktok_first_comment",
            "label": "Tambah first comment",
            "comment": first_comment,
            "retry_max": 2,
            **_d,
        })

    return steps
