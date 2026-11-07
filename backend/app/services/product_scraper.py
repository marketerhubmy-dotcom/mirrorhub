import re
import uuid
from pathlib import Path
from urllib.parse import urlparse, urlunparse, parse_qs

import httpx
from bs4 import BeautifulSoup

UPLOAD_DIR = Path(__file__).parent.parent.parent / "uploads"

# Only these domains are permitted — no arbitrary URL execution
ALLOWED_DOMAINS = {
    "shop.tiktok.com",
    "vt.tiktok.com",
    "www.tiktok.com",
    "tiktok.com",
    "affiliate.tiktok.com",
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ms-MY,ms;q=0.9,en-US;q=0.8",
}

_MAX_RESPONSE_BYTES = 2 * 1024 * 1024  # 2 MB cap


def validate_url(url: str) -> tuple[bool, str]:
    """
    Return (ok, error_message). Checks:
    - Not empty
    - Parseable
    - Domain is in ALLOWED_DOMAINS
    """
    url = url.strip()
    if not url:
        return False, "URL kosong."
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "URL tidak sah."
    if parsed.scheme not in ("http", "https"):
        return False, "URL mesti bermula dengan http:// atau https://."
    host = parsed.netloc.lower().lstrip("www.")
    # Accept if any allowed domain matches as suffix
    if not any(parsed.netloc.lower() == d or parsed.netloc.lower().endswith("." + d) for d in ALLOWED_DOMAINS):
        return False, (
            f"Domain '{parsed.netloc}' tidak disokong. "
            "Hanya TikTok Shop links (shop.tiktok.com, vt.tiktok.com) diterima."
        )
    return True, ""


def normalize_url(url: str) -> str:
    """
    Strip tracking params, fragments, and trailing slashes.
    shop.tiktok.com / www.tiktok.com: remove all query params (tracking noise).
    Short-link domains (vt.tiktok.com): strip fragment only; can't resolve without fetch.
    """
    url = url.strip()
    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "/"

    if "shop.tiktok.com" in parsed.netloc or "www.tiktok.com" in parsed.netloc:
        return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))

    # Other allowed domains: strip fragment, keep query params
    return urlunparse((parsed.scheme, parsed.netloc, path, parsed.params, parsed.query, ""))


def extract_product_id(url: str) -> str | None:
    """Extract product ID from TikTok Shop URL if present."""
    # shop.tiktok.com/view/product/1234567890
    m = re.search(r"/product/(\d+)", url)
    if m:
        return m.group(1)
    # item_id param
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    for key in ("item_id", "itemId", "id"):
        if key in qs:
            return qs[key][0]
    return None


def _extract_shop_name(soup: BeautifulSoup, html: str) -> str:
    """Best-effort extraction of TikTok Shop seller/shop name."""
    # Try structured meta first
    for selector in (
        {"property": "og:site_name"},
        {"name": "seller"},
        {"name": "shop"},
    ):
        tag = soup.find("meta", attrs=selector)
        if tag and tag.get("content"):
            return tag["content"].strip()
    # Try JSON-LD
    for script in soup.find_all("script", {"type": "application/ld+json"}):
        txt = script.string or ""
        m = re.search(r'"seller"\s*:\s*\{[^}]*"name"\s*:\s*"([^"]+)"', txt)
        if m:
            return m.group(1)
    # Try common class patterns
    for pattern in (r'"shopName"\s*:\s*"([^"]+)"', r'"seller_name"\s*:\s*"([^"]+)"'):
        m = re.search(pattern, html)
        if m:
            return m.group(1)
    return ""


async def fetch_product(url: str) -> dict:
    """
    Fetch product info from a TikTok Shop URL.

    Always returns a dict. On failure, sets fetch_failed=True and
    fetch_error to a human-readable message; other fields will be empty.
    """
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=15,
            headers=_HEADERS,
        ) as client:
            resp = await client.get(url)

        # Respect response size limit
        content = resp.content[:_MAX_RESPONSE_BYTES]
        html = content.decode(errors="replace")

        if resp.status_code in (401, 403):
            return _failed(url, f"TikTok menolak akses (HTTP {resp.status_code}). Cuba salin butiran produk secara manual.")
        if resp.status_code >= 400:
            return _failed(url, f"HTTP {resp.status_code} dari TikTok.")

        # Check if we were redirected to a login page
        final_url = str(resp.url)
        if "login" in final_url or "passport" in final_url:
            return _failed(url, "TikTok redirect ke login. Salin butiran produk secara manual.")

        # Detect bot-protection / CAPTCHA pages (Cloudflare, TikTok security check)
        bot_indicators = ("security check", "just a moment", "cf-browser-verification", "captcha")
        if any(ind in html.lower()[:2000] for ind in bot_indicators):
            return _failed(
                url,
                "TikTok mengesan bot dan memaparkan security check. "
                "Salin butiran produk secara manual dari TikTok Shop.",
            )

        soup = BeautifulSoup(html, "html.parser")

        def meta(prop: str) -> str:
            tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
            return (tag.get("content", "") if tag else "").strip()

        title = meta("og:title") or (soup.title.text.strip() if soup.title else "")
        image_url = meta("og:image")
        description = meta("og:description")
        shop_name = _extract_shop_name(soup, html)

        price = ""
        price_m = re.search(r"RM\s*[\d,]+\.?\d*", html)
        if price_m:
            price = price_m.group(0)

        # Extract rating and review count if visible
        rating = ""
        rating_m = re.search(r'"rating"\s*:\s*([\d.]+)', html)
        if rating_m:
            rating = rating_m.group(1)

        # Clean up title (TikTok often appends " | TikTok Shop" suffix)
        title = re.sub(r"\s*[\|–-]\s*TikTok.*$", "", title).strip()

        # Reject titles that are obviously bot-block pages, not products
        _BAD_TITLES = {"security check", "just a moment", "access denied", "403 forbidden", ""}
        if not title or title.lower() in _BAD_TITLES:
            return _failed(url, "Tidak dapat ekstrak nama produk dari halaman. Cuba salin butiran produk secara manual.")

        return {
            "fetch_failed": False,
            "fetch_error": "",
            "title": title,
            "shop_name": shop_name,
            "description": description,
            "image_url": image_url,
            "price": price,
            "rating": rating,
            "final_url": final_url,
            "product_id": extract_product_id(final_url) or extract_product_id(url),
        }

    except httpx.TimeoutException:
        return _failed(url, "Timeout semasa cuba fetch produk. Semak sambungan internet.")
    except Exception as exc:
        return _failed(url, f"Ralat semasa fetch: {exc}")


def _failed(url: str, reason: str) -> dict:
    return {
        "fetch_failed": True,
        "fetch_error": reason,
        "title": "",
        "shop_name": "",
        "description": "",
        "image_url": "",
        "price": "",
        "rating": "",
        "final_url": url,
        "product_id": extract_product_id(url),
    }


async def download_image(image_url: str) -> str | None:
    """Download product image, save to uploads, return filename."""
    if not image_url:
        return None
    UPLOAD_DIR.mkdir(exist_ok=True)
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
            resp = await client.get(image_url)
        if resp.status_code != 200:
            return None
        ct = resp.headers.get("content-type", "image/jpeg")
        ext = ".png" if "png" in ct else ".jpg"
        filename = f"{uuid.uuid4().hex}{ext}"
        (UPLOAD_DIR / filename).write_bytes(resp.content[:_MAX_RESPONSE_BYTES])
        return filename
    except Exception:
        return None
