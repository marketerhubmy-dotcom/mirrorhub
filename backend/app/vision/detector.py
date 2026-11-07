import re

from .ocr import OcrResult
from .state import ScreenType


def classify_screen(ocr: OcrResult) -> tuple[ScreenType, float]:
    """Rule-based screen classification from OCR results."""
    all_text = {t.lower() for t in ocr.visible_text}
    btn_texts = {b.text.lower() for b in ocr.buttons}
    combined = all_text | btn_texts

    # Generation Screen (YouTube Create generating video)
    if any(t in combined for t in ["generating", "creating your video"]) or detect_progress(ocr) is not None:
        return ScreenType.GENERATION_SCREEN, 0.85

    # Export / Continue after generation
    if any(t in btn_texts for t in ["continue", "export"]) and any(
        t in combined for t in ["share", "done", "next", "tiktok"]
    ):
        return ScreenType.EXPORT_SCREEN, 0.82

    # Share Sheet
    if "share" in combined and any(
        t in combined for t in ["tiktok", "instagram", "youtube", "copy link", "more options"]
    ):
        return ScreenType.SHARE_SHEET, 0.85

    # Gallery / Image Picker
    if any(t in combined for t in ["gallery", "recents", "all photos", "camera roll"]):
        return ScreenType.GALLERY_PICKER, 0.82

    # Permission Dialog
    if any(t in combined for t in ["allow", "deny", "don't allow"]) and (
        "permission" in combined or "access" in combined or len(combined) < 12
    ):
        return ScreenType.PERMISSION_DIALOG, 0.85

    # Error Dialog
    if any(t in combined for t in ["error", "failed", "something went wrong", "unable to"]):
        return ScreenType.ERROR_DIALOG, 0.82

    # Confirmation Dialog
    if ocr.dialogs or (
        any(t in btn_texts for t in ["ok", "cancel", "confirm", "dismiss"])
        and len(ocr.visible_text) < 12
    ):
        return ScreenType.CONFIRMATION_DIALOG, 0.75

    # Loading (few elements, spinner-like)
    if detect_loading(ocr):
        return ScreenType.LOADING, 0.70

    # Home / Main screen
    if any(t in combined for t in ["new project", "my projects", "templates", "create"]):
        return ScreenType.HOME, 0.85

    return ScreenType.UNKNOWN, 0.30


def detect_loading(ocr: OcrResult) -> bool:
    loading_terms = {"loading", "please wait", "processing", "connecting", "initializing"}
    text_lower = {t.lower() for t in ocr.visible_text}
    return bool(loading_terms & text_lower) or (
        len(ocr.buttons) == 0 and len(ocr.visible_text) < 4
    )


def detect_errors(ocr: OcrResult) -> list[str]:
    error_terms = {"error", "failed", "something went wrong", "no network", "unable to", "crash"}
    return [t for t in ocr.visible_text if any(e in t.lower() for e in error_terms)]


def detect_progress(ocr: OcrResult) -> float | None:
    """Extract progress percentage from visible text, if any."""
    for text in ocr.visible_text:
        m = re.search(r'(\d{1,3})\s*%', text)
        if m:
            val = float(m.group(1))
            if 0.0 <= val <= 100.0:
                return val
    return None


def detect_image_placeholders(ocr: OcrResult) -> list[str]:
    placeholder_terms = {"add image", "add media", "insert image", "upload photo", "tap to add"}
    return [t for t in ocr.visible_text if any(p in t.lower() for p in placeholder_terms)]
