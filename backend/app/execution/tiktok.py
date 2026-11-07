"""
TikTok Publisher step handlers — MVP 0.6.1

Key changes vs 0.2:
  - _insert_caption: logs char count, verifies field not empty after insert
  - _open_product_selector: waits for Add link sheet before tapping Product
  - _search_product: clears field before inserting exact search term
  - _match_product: exact-match step (new) — finds product card by normalized name
  - _attach_product: taps Add button associated with the matched card
  - _verify_product: post-editor check that product name is visible (new)
"""
import asyncio
import logging
import re
import subprocess
from pathlib import Path

from .state_machine import StepResult

logger = logging.getLogger(__name__)


def _adb() -> Path:
    base = Path(__file__).parent.parent.parent.parent
    return base / "tools" / "scrcpy" / "scrcpy-win64-v4.0" / "adb.exe"


async def _run(adb_address: str, *args: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        str(_adb()), "-s", adb_address, *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    out, _ = await proc.communicate()
    return out.decode(errors="replace")


async def _get_screen_size(adb_address: str) -> tuple[int, int]:
    raw = await _run(adb_address, "shell", "wm", "size")
    try:
        part = raw.strip().split(":")[-1].strip()
        w, h = part.split("x")
        return (int(w), int(h))
    except Exception:
        return (1080, 2400)


async def _tap_rel(adb_address: str, rx: float, ry: float) -> None:
    w, h = await _get_screen_size(adb_address)
    await _run(adb_address, "shell", "input", "tap",
               str(int(w * rx)), str(int(h * ry)))


async def _swipe_rel(
    adb_address: str, x1: float, y1: float, x2: float, y2: float, ms: int = 300
) -> None:
    w, h = await _get_screen_size(adb_address)
    await _run(adb_address, "shell", "input", "swipe",
               str(int(w * x1)), str(int(h * y1)),
               str(int(w * x2)), str(int(h * y2)),
               str(ms))


# ── Text input ────────────────────────────────────────────────────────────────

def _shell_single_quote(text: str) -> str:
    return "'" + text.replace("'", "'\\''") + "'"


async def _clipboard_paste(adb_address: str, text: str) -> None:
    """
    Set Android clipboard via cmd clipboard set-text (Android 12+) + KEYCODE_PASTE.
    Falls back to _type_safe() on older Android or command failure.
    """
    quoted = _shell_single_quote(text)
    result = await _run(adb_address, "shell", "cmd", "clipboard", "set-text", quoted)

    if result.strip() and any(
        kw in result.lower()
        for kw in ("error", "exception", "not found", "unknown command", "implementation")
    ):
        await _type_safe(adb_address, text)
        return

    await asyncio.sleep(0.3)
    await _run(adb_address, "shell", "input", "keyevent", "KEYCODE_PASTE")
    await asyncio.sleep(0.5)


async def _type_safe(adb_address: str, text: str) -> None:
    """Type via input text with correct shell escaping. # is escaped, not dropped."""
    ESCAPES = [
        ('\\', '\\\\'), ('"', '\\"'), ("'", "\\'"), ('$', '\\$'),
        ('(', '\\('), (')', '\\)'), ('&', '\\&'), ('|', '\\|'),
        (';', '\\;'), ('<', '\\<'), ('>', '\\>'), ('`', '\\`'),
        ('!', '\\!'), ('#', '\\#'),
    ]
    for line in text.split('\n'):
        stripped = line.strip()
        if stripped:
            safe = stripped
            for char, esc in ESCAPES:
                safe = safe.replace(char, esc)
            adb_text = safe.replace(' ', '%s')
            await _run(adb_address, "shell", "input", "text", adb_text)
        await _run(adb_address, "shell", "input", "keyevent", "KEYCODE_ENTER")
        await asyncio.sleep(0.15)


# ── Vision helpers ────────────────────────────────────────────────────────────

async def _vision(adb_address: str, step: dict):
    device_id = step.get("device_id", "")
    if not device_id:
        return None
    try:
        from app.vision.analyzer import analyze_screen
        return await analyze_screen(adb_address, device_id)
    except Exception:
        return None


async def _tap_vision_button(
    adb_address: str, step: dict, *candidates: str,
    fallback_rx: float | None = None, fallback_ry: float | None = None,
) -> bool:
    try:
        from app.vision.matcher import find_button as _find_btn
        analysis = await _vision(adb_address, step)
        if analysis:
            btn = _find_btn(analysis, *candidates)
            if btn and btn.x > 0 and btn.y > 0:
                await _run(adb_address, "shell", "input", "tap", str(btn.x), str(btn.y))
                return True
    except Exception:
        pass

    await _run(adb_address, "shell", "uiautomator", "dump", "/sdcard/mh_ui.xml")
    xml = await _run(adb_address, "shell", "cat", "/sdcard/mh_ui.xml")
    for candidate in candidates:
        for pat in [
            rf'text="{re.escape(candidate)}"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
            rf'content-desc="{re.escape(candidate)}"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
        ]:
            m = re.search(pat, xml, re.IGNORECASE)
            if m:
                x = (int(m.group(1)) + int(m.group(3))) // 2
                y = (int(m.group(2)) + int(m.group(4))) // 2
                await _run(adb_address, "shell", "input", "tap", str(x), str(y))
                return True

    if fallback_rx is not None and fallback_ry is not None:
        await _tap_rel(adb_address, fallback_rx, fallback_ry)
        return True
    return False


async def _ui_xml(adb_address: str) -> str:
    await _run(adb_address, "shell", "uiautomator", "dump", "/sdcard/mh_ui.xml")
    return await _run(adb_address, "shell", "cat", "/sdcard/mh_ui.xml")


# ── Step handlers ─────────────────────────────────────────────────────────────

async def _launch(adb_address: str, step: dict) -> StepResult:
    from app.apps.tiktok.constants import PACKAGE_NAME, PACKAGE_NAME_ALT, LAUNCH_TIMEOUT
    for package in (PACKAGE_NAME, PACKAGE_NAME_ALT):
        await _run(adb_address, "shell", "monkey", "-p", package,
                   "-c", "android.intent.category.LAUNCHER", "1")
        await asyncio.sleep(2)

    device_id = step.get("device_id", "")
    if device_id:
        try:
            from app.vision.analyzer import wait_until
            analysis = await wait_until(
                adb_address, device_id,
                button="For You",
                timeout=LAUNCH_TIMEOUT,
                poll_interval=2.0,
            )
            if analysis.has_button("For You", "Following", "Explore", "Create"):
                return StepResult.SUCCESS
            return StepResult.RETRY
        except Exception:
            pass
    await asyncio.sleep(5)
    return StepResult.SUCCESS


async def _verify_home(adb_address: str, step: dict) -> StepResult:
    analysis = await _vision(adb_address, step)
    if analysis:
        if analysis.has_button("For You", "Following", "Explore", "+"):
            return StepResult.SUCCESS
        return StepResult.RETRY
    await asyncio.sleep(2)
    return StepResult.SUCCESS


async def _push_video(adb_address: str, step: dict) -> StepResult:
    local       = step.get("local", "")
    device_path = step.get("device_path", "/sdcard/DCIM/mh_tiktok.mp4")
    device_dir  = "/".join(device_path.split("/")[:-1])
    await _run(adb_address, "shell", "mkdir", "-p", device_dir)

    proc = await asyncio.create_subprocess_exec(
        str(_adb()), "-s", adb_address,
        "push", local, device_path,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    await proc.communicate()
    if proc.returncode != 0:
        return StepResult.RETRY

    await _run(adb_address, "shell", "am", "broadcast",
               "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE",
               "-d", f"file://{device_path}")
    await asyncio.sleep(1)
    return StepResult.SUCCESS


async def _open_upload(adb_address: str, step: dict) -> StepResult:
    found = await _tap_vision_button(
        adb_address, step, "+", "Create", "Upload",
        fallback_rx=0.5, fallback_ry=0.95,
    )
    await asyncio.sleep(2)
    if not found:
        return StepResult.RETRY
    await _tap_vision_button(
        adb_address, step, "Upload", fallback_rx=0.85, fallback_ry=0.92
    )
    await asyncio.sleep(2)
    return StepResult.SUCCESS


async def _select_video(adb_address: str, step: dict) -> StepResult:
    await _tap_rel(adb_address, 0.17, 0.22)
    await asyncio.sleep(1)
    found = await _tap_vision_button(
        adb_address, step, "Next", "Continue", "OK",
        fallback_rx=0.85, fallback_ry=0.07,
    )
    await asyncio.sleep(2)
    return StepResult.SUCCESS if found else StepResult.RETRY


async def _verify_preview(adb_address: str, step: dict) -> StepResult:
    from app.apps.tiktok.constants import UPLOAD_TIMEOUT
    device_id = step.get("device_id", "")
    if device_id:
        try:
            from app.vision.analyzer import wait_until
            analysis = await wait_until(
                adb_address, device_id,
                button="Next",
                timeout=UPLOAD_TIMEOUT,
                poll_interval=2.0,
            )
            if analysis.has_button("Next", "Edit", "Adjust"):
                return StepResult.SUCCESS
            return StepResult.RETRY
        except Exception:
            pass
    await asyncio.sleep(3)
    return StepResult.SUCCESS


async def _tap_next(adb_address: str, step: dict) -> StepResult:
    found = await _tap_vision_button(
        adb_address, step, "Next",
        fallback_rx=0.85, fallback_ry=0.07,
    )
    await asyncio.sleep(3)
    return StepResult.SUCCESS if found else StepResult.RETRY


async def _insert_caption(adb_address: str, step: dict) -> StepResult:
    """
    Type caption + hashtags into the TikTok post description field.

    Uses the exact approved caption string from the step dict (built in routes.py
    as caption.strip() + newline + hashtags).  Never regenerates content here.

    Logs the source char count and verifies the field is not empty after insert.
    """
    caption = step.get("caption", "")
    if not caption:
        return StepResult.SKIP

    source_chars = step.get("caption_char_count", len(caption))
    logger.info("tiktok_insert_caption: inserting %d chars from approved caption", source_chars)

    # Accept "Music Usage Confirmation" if present.
    # This is an INLINE checkbox at the bottom of the post editor (not a blocking modal).
    # Just tick the checkbox and continue — there is no separate Confirm/OK button.
    # Correct fallback: x≈0.3 (center of label), y≈0.714 ("I accept" row at bottom of form).
    # Do NOT tap anything afterward; the caption field at the top is still reachable.
    xml_pre = await _ui_xml(adb_address)
    if "music usage" in xml_pre.lower() or "i accept" in xml_pre.lower():
        logger.info("tiktok_insert_caption: accepting music usage confirmation (inline checkbox)")
        await _tap_vision_button(adb_address, step, "I accept", fallback_rx=0.3, fallback_ry=0.714)
        await asyncio.sleep(1.0)

    found = await _tap_vision_button(
        adb_address, step,
        "Add description...", "Describe your video", "Add a caption", "Caption",
        fallback_rx=0.33, fallback_ry=0.196,  # (357/1080, 469/2400)
    )
    await asyncio.sleep(0.5)

    # Clear existing content
    await _run(adb_address, "shell", "input", "keyevent", "KEYCODE_CTRL_A")
    await asyncio.sleep(0.2)
    await _run(adb_address, "shell", "input", "keyevent", "KEYCODE_DEL")
    await asyncio.sleep(0.2)

    # Type caption body and hashtags line by line.
    # DO NOT send KEYCODE_ENTER after the last (hashtag) line — TikTok replaces
    # the final hashtag with an autocomplete suggestion on Enter.
    lines = caption.split('\n')
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped:
            safe = stripped
            for char, esc in [
                ('\\', '\\\\'), ('"', '\\"'), ("'", "\\'"), ('$', '\\$'),
                ('(', '\\('), (')', '\\)'), ('&', '\\&'), ('|', '\\|'),
                (';', '\\;'), ('<', '\\<'), ('>', '\\>'), ('`', '\\`'),
                ('!', '\\!'), ('#', '\\#'),
            ]:
                safe = safe.replace(char, esc)
            await _run(adb_address, "shell", "input", "text", safe.replace(' ', '%s'))
        # Only send ENTER between lines, not after the last one
        if i < len(lines) - 1:
            await _run(adb_address, "shell", "input", "keyevent", "KEYCODE_ENTER")
            await asyncio.sleep(0.15)
    await asyncio.sleep(1)

    # Verify field not empty via uiautomator
    xml = await _ui_xml(adb_address)
    is_empty = (
        'text="Add description..."' in xml
        or 'text="Describe your video"' in xml
        or 'text="Add a caption"' in xml
    )
    if is_empty:
        logger.warning("tiktok_insert_caption: field appears empty after insert — retrying")
        await _run(adb_address, "shell", "input", "keyevent", "KEYCODE_BACK")
        return StepResult.RETRY

    logger.info("tiktok_insert_caption: caption inserted successfully")
    # Do NOT press BACK here — if keyboard auto-dismissed before this runs, BACK would
    # navigate away from the post editor.  Keyboard dismissal is handled by
    # _open_product_selector which checks IME state before acting.
    await asyncio.sleep(0.5)
    return StepResult.SUCCESS if found else StepResult.RETRY


async def _advance_to_post_editor(adb_address: str, step: dict) -> StepResult:
    """
    After ytcreate_share TikTok opens with either:
    - The video editor ("Add sound", "AutoCut", "Next") — UIAutomator is nearly blind to
      it (TikTok custom views), so XML is sparse (<BLANK_THRESHOLD nodes).
    - The post editor directly — UIAutomator sees many elements (edit cover, everyone can
      view, etc.).

    Strategy:
    1. Wait 4 s for the share-intent transition to finish.
    2. Check UIAutomator for post-editor markers → SUCCESS if found.
    3. Sparse XML (< BLANK_THRESHOLD nodes) → video editor → tap "Next".
    4. Dense XML but no markers → wrong screen (shop, DM, etc.) → press BACK.

    "Next" button position on Pixel 6 / TikTok video editor (1080×2400): rx≈0.578, ry≈0.712
    """
    POST_EDITOR_MARKERS = (
        "add description", "describe your video", "add a caption",
        "edit cover", "everyone can view", "who can watch",
        "allow duet", "save to device",
    )
    # TikTok's For You / home feed — do NOT press BACK here; that cancels the pending
    # share-intent upload and leaves TikTok on the wrong screen permanently.  Just wait.
    FOR_YOU_MARKERS = ("for you", "following", "community", "friends tab")
    NEXT_RX, NEXT_RY = 0.578, 0.712
    BLANK_THRESHOLD = 10  # <10 nodes → UIAutomator is blind → assume video editor

    await asyncio.sleep(4)  # let TikTok finish the share-intent transition

    for attempt in range(8):
        xml = await _ui_xml(adb_address)
        xml_lower = xml.lower()

        if any(kw in xml_lower for kw in POST_EDITOR_MARKERS):
            logger.info("_advance_to_post_editor: post editor confirmed (attempt %d)", attempt)
            return StepResult.SUCCESS

        node_count = xml.count("<node ")
        logger.info(
            "_advance_to_post_editor: attempt %d — no markers, node_count=%d",
            attempt, node_count,
        )

        if node_count < BLANK_THRESHOLD:
            # Sparse XML → video editor (UIAutomator blind to TikTok custom views)
            await _tap_rel(adb_address, NEXT_RX, NEXT_RY)
            await asyncio.sleep(4)
        elif any(kw in xml_lower for kw in FOR_YOU_MARKERS):
            # For You feed visible — TikTok share is still processing. Wait, do NOT press
            # BACK (that would cancel the pending upload and strand us on the home screen).
            logger.warning(
                "_advance_to_post_editor: For You feed detected (node_count=%d) — waiting",
                node_count,
            )
            await asyncio.sleep(4)
        else:
            # Dense XML, unknown wrong screen — press BACK
            logger.warning(
                "_advance_to_post_editor: %d nodes but no markers — pressing BACK",
                node_count,
            )
            await _run(adb_address, "shell", "input", "keyevent", "KEYCODE_BACK")
            await asyncio.sleep(3)

    xml = await _ui_xml(adb_address)
    if any(kw in xml.lower() for kw in POST_EDITOR_MARKERS):
        return StepResult.SUCCESS

    logger.warning("_advance_to_post_editor: post editor not confirmed after all attempts")
    return StepResult.RETRY


async def _edit_cover(adb_address: str, step: dict) -> StepResult:
    """
    Open TikTok cover editor after the video is loaded in the post-details screen.

    Flow:
      1. Find and tap the cover-edit button (Edit cover / Select cover / Cover).
      2. Select a usable frame (swipe slightly to find a non-black frame, then confirm).
      3. If TikTok's text tool is available, paste the cover_hook text.
      4. Save / confirm and return to the post editor.

    On failure, returns SKIP (not RETRY) so the rest of the pipeline continues —
    the cover hook must then be added manually before posting.

    Navigation to the post editor is handled by the preceding tiktok_advance_to_post_editor
    step; this function assumes it starts on the post editor already.
    """
    cover_hook = step.get("cover_hook", "")

    # ── 1. Open cover editor ─────────────────────────────────────────────────
    # Deliberately omit "Edit" from candidates — it matches the video editor's Edit
    # toolbar and causes false taps if the advance step didn't fully navigate.
    found = await _tap_vision_button(
        adb_address, step,
        "Edit cover", "Select cover", "Cover",
        fallback_rx=0.5, fallback_ry=0.72,
    )
    if not found:
        # Cover editor not reachable — skip gracefully
        return StepResult.SKIP
    await asyncio.sleep(2)

    # ── 2. Select a frame ────────────────────────────────────────────────────
    # Swipe the frame scrubber slightly right to avoid a black first frame
    xml = await _ui_xml(adb_address)
    if "cover" in xml.lower() or "frame" in xml.lower() or "select" in xml.lower():
        # Scrub right by ~10% of width from centre of scrubber area (≈ y 0.88)
        await _swipe_rel(adb_address, 0.5, 0.88, 0.6, 0.88, 300)
        await asyncio.sleep(0.5)

    # ── 3. Add cover text if tool is available ───────────────────────────────
    text_inserted = False
    if cover_hook:
        xml = await _ui_xml(adb_address)
        has_text_tool = any(
            kw in xml.lower()
            for kw in ("add text", "text tool", "sticker")
        ) or any(
            'text="T"' in n or 'content-desc="Text"' in n or 'content-desc="Add text"' in n
            for n in xml.split("<node ")
        )
        if has_text_tool:
            await _tap_vision_button(
                adb_address, step, "Text", "Add text", "T",
                fallback_rx=0.5, fallback_ry=0.10,
            )
            await asyncio.sleep(0.5)
            await _clipboard_paste(adb_address, cover_hook)
            await asyncio.sleep(0.5)
            # Position text: tap centre-upper area (safe zone for cover)
            w, h = await _get_screen_size(adb_address)
            await _run(adb_address, "shell", "input", "tap", str(w // 2), str(int(h * 0.3)))
            await asyncio.sleep(0.3)
            # Confirm text entry
            await _tap_vision_button(
                adb_address, step, "Done", "OK", "Confirm",
                fallback_rx=0.85, fallback_ry=0.07,
            )
            await asyncio.sleep(0.5)
            text_inserted = True
        else:
            # Text tool not available — frame selected, cover hook must be added manually
            step["_cover_status"] = "FRAME_SELECTED_TEXT_MANUAL"
            step["_cover_hook_pending"] = cover_hook
            logger.info(
                "tiktok_edit_cover: text tool not found — frame selected, "
                "cover hook must be added manually before posting"
            )

    # ── 4. Save cover and return to post editor ──────────────────────────────
    await _tap_vision_button(
        adb_address, step, "Save", "Done", "Confirm", "Next",
        fallback_rx=0.85, fallback_ry=0.07,
    )
    await asyncio.sleep(2)

    if text_inserted:
        step["_cover_status"] = "TEXT_INSERTED"
        logger.info("tiktok_edit_cover: cover hook text inserted successfully")
    elif not cover_hook:
        step["_cover_status"] = "NO_HOOK"

    return StepResult.SUCCESS


async def _open_product_selector(adb_address: str, step: dict) -> StepResult:
    """
    Post Editor → tap Add link → wait for sheet → tap Product.

    "Shop" intentionally omitted — it navigates to the Profile Shop tab.
    Waits up to 5s for the Add link bottom sheet to appear before tapping Product.
    """
    # Dismiss keyboard ONLY if it is actually showing (mInputShown=true).
    # Sending KEYCODE_BACK when keyboard is NOT showing navigates out of the post editor.
    ime_info = await _run(adb_address, "shell", "dumpsys", "input_method")
    if "mInputShown=true" in ime_info:
        logger.info("_open_product_selector: IME visible — dismissing keyboard")
        await _run(adb_address, "shell", "input", "keyevent", "KEYCODE_BACK")
        await asyncio.sleep(0.8)
    else:
        logger.info("_open_product_selector: keyboard not showing — proceeding directly")
        await asyncio.sleep(0.3)

    # Tap "Add link" row (y≈0.383 from post editor screenshot)
    found = await _tap_vision_button(
        adb_address, step,
        "Add link", "Product link", "Add product",
        fallback_rx=0.5, fallback_ry=0.383,
    )
    if not found:
        return StepResult.RETRY
    await asyncio.sleep(1.5)

    # Wait for the Add link sheet — check for "LIVE Events" which is the second option
    # in this account's sheet and does NOT appear anywhere on the post editor.
    # (This account's sheet only shows: Product + LIVE Events — no Music/Location/etc.)
    sheet_ready = False
    for _ in range(6):
        xml = await _ui_xml(adb_address)
        if any(kw in xml.lower() for kw in ("live events", "live event")):
            sheet_ready = True
            break
        await asyncio.sleep(1)
    if not sheet_ready:
        logger.warning("_open_product_selector: Add link sheet did not appear (no 'LIVE Events' found)")
        return StepResult.RETRY

    # Tap "Product" in the sheet via UIAutomator node match first, then vision fallback.
    # The sheet lists: Product (top) → Music → Location → …
    # Fallback coordinate MUST target the top option in the sheet (≈ ry=0.66), NOT ry=0.733
    # which lands on the Music row and opens "Commercial Sounds" instead.
    xml = await _ui_xml(adb_address)
    tapped_product = False
    for node_text in ("Product", "Products", "product"):
        import re as _re
        m = _re.search(
            rf'text="{node_text}"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
            xml,
        )
        if not m:
            m = _re.search(
                rf'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^>]*text="{node_text}"',
                xml,
            )
        if m:
            x = (int(m.group(1)) + int(m.group(3))) // 2
            y = (int(m.group(2)) + int(m.group(4))) // 2
            await _run(adb_address, "shell", "input", "tap", str(x), str(y))
            logger.info("_open_product_selector: tapped '%s' node at (%d,%d)", node_text, x, y)
            tapped_product = True
            break

    # Infer "Product" (top row) position from sibling items that UIAutomator CAN see.
    # Sheet order: Product → Music → Location → Sticker → Poll
    # Product uses a custom view so UIAutomator misses its text, but Music/Location are visible.
    if not tapped_product:
        for ref_text, n_above in (("Music", 1), ("Location", 2)):
            m = re.search(
                rf'(?:text|content-desc)="{re.escape(ref_text)}"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
                xml, re.IGNORECASE,
            )
            if not m:
                m = re.search(
                    rf'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^>]*(?:text|content-desc)="{re.escape(ref_text)}"',
                    xml, re.IGNORECASE,
                )
            if m:
                ref_top = int(m.group(2))
                ref_bot = int(m.group(4))
                ref_cx = (int(m.group(1)) + int(m.group(3))) // 2
                row_h = ref_bot - ref_top
                prod_y = ref_top - n_above * row_h + row_h // 2
                await _run(adb_address, "shell", "input", "tap", str(ref_cx), str(prod_y))
                logger.info(
                    "_open_product_selector: inferred Product at (%d,%d) from '%s' bounds",
                    ref_cx, prod_y, ref_text,
                )
                tapped_product = True
                break

    if not tapped_product:
        logger.warning("_open_product_selector: Product node not found — using coordinate fallback")
        await _tap_vision_button(
            adb_address, step, "Product", "Products",
            fallback_rx=0.5, fallback_ry=0.56,   # first row of Add link sheet (above Music)
        )

    await asyncio.sleep(2)

    # Guard: if we're somehow back on the video editor (advance step incomplete), retry.
    xml_after = await _ui_xml(adb_address)
    xml_after_lower = xml_after.lower()
    VIDEO_EDITOR_MARKERS = ("add sound", "autocut", "your story")
    if any(kw in xml_after_lower for kw in VIDEO_EDITOR_MARKERS):
        logger.warning("_open_product_selector: still on video editor — returning RETRY")
        return StepResult.RETRY

    # Recovery: if we accidentally opened "Commercial Sounds" or music page, go back.
    # Only match "commercial sounds" or "music library" — NOT bare "sounds" which also
    # appears in "Add sound" on the video editor toolbar.
    if any(kw in xml_after_lower for kw in ("commercial sounds", "music library")):
        logger.warning("_open_product_selector: landed on music page — pressing BACK and retrying")
        await _run(adb_address, "shell", "input", "keyevent", "KEYCODE_BACK")
        await asyncio.sleep(1.5)
        return StepResult.RETRY

    return StepResult.SUCCESS


async def _wait_product_page(adb_address: str, step: dict) -> StepResult:
    """
    Poll until the TikTok Shop product-search page is fully loaded.

    Accepts: "Search products", "Add products", "TikTok Shop", "Search", search input,
             or any product listing indicator.
    Rejects: loading spinner still showing (heuristic: empty XML body).
    Timeout: step["wait_seconds"] (default 20 s).
    """
    wait_sec = int(step.get("wait_seconds", 20))
    poll_interval = 1.5
    device_id = step.get("device_id", "")

    # Keywords that appear on the product search page.
    # "add product links" is the exact page title (screenshot confirmed).
    # "your showcase" / "from showcase" are section headers visible on that page.
    # "search products" is the search bar placeholder text.
    # NOTE: "add link" is intentionally ABSENT — it also appears in "Add product links".
    READY_KEYWORDS = (
        "search products",
        "add product links",
        "your showcase",
        "from showcase",
        "add products",
        "tiktok shop",
        "no result",
        "product not found",
    )
    # Markers unique to the post editor — must NOT include "add link" because
    # that matches "Add product links" (the product page title).
    POST_EDITOR_MARKERS = ("everyone can view", "describe your video")

    loop = asyncio.get_running_loop()
    deadline = loop.time() + wait_sec
    uia_fail_streak = 0
    # TikTok's product showcase has live-updating content that causes UIAutomator to
    # block ~11s then fail. The post editor NEVER fails UIAutomator. 2 consecutive
    # failures (~25s) is a reliable signal we're on the product page.
    UIA_FAIL_LIMIT = 2

    while loop.time() < deadline:
        await asyncio.sleep(poll_interval)

        # Delete stale XML first so we can detect whether this dump succeeded.
        await _run(adb_address, "shell", "rm", "-f", "/sdcard/mh_ui.xml")
        await _run(adb_address, "shell", "uiautomator", "dump", "/sdcard/mh_ui.xml")
        xml = await _run(adb_address, "shell", "cat", "/sdcard/mh_ui.xml")

        if not xml.strip() or "<hierarchy" not in xml:
            # UIAutomator failed — product page has live content, this is expected.
            uia_fail_streak += 1
            logger.info(
                "_wait_product_page: UIAutomator failed (streak=%d/%d) — product page likely open",
                uia_fail_streak, UIA_FAIL_LIMIT,
            )
            if uia_fail_streak >= UIA_FAIL_LIMIT:
                logger.info("_wait_product_page: returning SUCCESS after %d UIAutomator failures", uia_fail_streak)
                return StepResult.SUCCESS
            continue

        uia_fail_streak = 0
        xml_lower = xml.lower()

        if any(m in xml_lower for m in POST_EDITOR_MARKERS):
            logger.debug("_wait_product_page: still on post editor, waiting...")
            continue

        if any(kw in xml_lower for kw in READY_KEYWORDS):
            return StepResult.SUCCESS

        # Vision fallback
        if device_id:
            try:
                from app.vision.analyzer import analyze_screen
                analysis = await analyze_screen(adb_address, device_id)
                visible_lower = " ".join(t.lower() for t in analysis.visible_text)
                if any(kw in visible_lower for kw in READY_KEYWORDS):
                    return StepResult.SUCCESS
            except Exception:
                pass

    return StepResult.RETRY


async def _search_product(adb_address: str, step: dict) -> StepResult:
    """
    Search TikTok Shop by the exact persisted tiktok_product_name.

    Steps:
      1. Locate search control — fallback_ry=0.145 (physical y≈349 on Pixel 6, confirmed).
      2. Tap, clear, paste exact term, submit with ENTER.
      3. Wait for results: UIAutomator failure on the live results page = SUCCESS
         (SparkActivity always blocks UIAutomator; post editor never does).
    """
    search_term = step.get("search_term", "")
    if not search_term:
        return StepResult.SKIP

    logger.info("tiktok_search_product: searching exact term (%d chars)", len(search_term))

    # Tap search field — confirmed at physical y≈349 (ry=0.145) on Pixel 6
    await _tap_vision_button(
        adb_address, step, "Search", "Search products",
        fallback_rx=0.5, fallback_ry=0.145,
    )
    await asyncio.sleep(0.6)

    # Clear any pre-existing text with select-all then delete
    await _run(adb_address, "shell", "input", "keyevent", "KEYCODE_CTRL_A")
    await asyncio.sleep(0.15)
    await _run(adb_address, "shell", "input", "keyevent", "KEYCODE_DEL")
    await asyncio.sleep(0.15)

    # Paste exact term via clipboard (handles spaces correctly)
    await _clipboard_paste(adb_address, search_term)
    await asyncio.sleep(0.6)
    await _run(adb_address, "shell", "input", "keyevent", "KEYCODE_ENTER")
    await asyncio.sleep(4)  # let search results load

    # Search results page is SparkActivity (live content) — UIAutomator always fails there.
    # Post editor UIAutomator always succeeds. So: UIA failure = we're on results page = SUCCESS.
    await _run(adb_address, "shell", "rm", "-f", "/sdcard/mh_ui.xml")
    await _run(adb_address, "shell", "uiautomator", "dump", "/sdcard/mh_ui.xml")
    xml = await _run(adb_address, "shell", "cat", "/sdcard/mh_ui.xml")

    if not xml.strip() or "<hierarchy" not in xml:
        logger.info("tiktok_search_product: UIAutomator failed → search results page open, SUCCESS")
        step["_search_uia_failed"] = True
        return StepResult.SUCCESS

    # UIAutomator succeeded — check if search term or Add button visible
    xml_lower = xml.lower()
    if search_term.split()[0].lower() in xml_lower or "add" in xml_lower:
        return StepResult.SUCCESS

    logger.warning("tiktok_search_product: results unclear, proceeding optimistically")
    return StepResult.SUCCESS


def _normalize(text: str) -> str:
    """Normalize product name for comparison: lowercase, collapse spaces, strip."""
    return re.sub(r"\s+", " ", text.lower().strip())


async def _match_product(adb_address: str, step: dict) -> StepResult:
    """
    Inspect TikTok Shop search result cards and find the exact product match.

    Search results are on a SparkActivity page — UIAutomator always fails there.
    When UIA fails we cannot read card names; signal _attach_product to use
    coordinate fallback via step["_match_uia_failed"]=True.
    When UIA succeeds (rare), try exact normalized name match first.
    """
    product_name = step.get("product_name", "")
    if not product_name:
        return StepResult.SKIP

    target = _normalize(product_name)

    # Use rm-before-dump to detect UIAutomator failure reliably
    await _run(adb_address, "shell", "rm", "-f", "/sdcard/mh_ui.xml")
    await _run(adb_address, "shell", "uiautomator", "dump", "/sdcard/mh_ui.xml")
    xml = await _run(adb_address, "shell", "cat", "/sdcard/mh_ui.xml")

    if not xml.strip() or "<hierarchy" not in xml:
        # UIAutomator failed = live SparkActivity page = search results are showing
        logger.info(
            "tiktok_match_product: UIAutomator failed on results page — "
            "signalling _attach_product to use coordinate fallback"
        )
        step["_match_uia_failed"] = True
        return StepResult.SUCCESS

    nodes = xml.split("<node ")

    # Collect all visible text nodes with their bounds
    candidates: list[tuple[str, str]] = []
    for node_str in nodes:
        for attr in ("text=", "content-desc="):
            m = re.search(attr + r'"([^"]+)"', node_str)
            if m:
                raw_text = m.group(1)
                if len(raw_text) < 5 or raw_text.lower() in ("add", "select", "search", "cancel"):
                    continue
                bm = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', node_str)
                if bm:
                    candidates.append((_normalize(raw_text), bm.group(0)))

    # Exact match
    for norm_text, bounds_str in candidates:
        if norm_text == target:
            step["_matched_bounds"] = bounds_str
            step["_matched_text"] = norm_text
            logger.info("tiktok_match_product: exact match — '%s'", norm_text)
            return StepResult.SUCCESS

    # Partial match (first word)
    first_word = target.split()[0] if target else ""
    for norm_text, bounds_str in candidates:
        if first_word and first_word in norm_text:
            step["_matched_bounds"] = bounds_str
            step["_matched_text"] = norm_text
            logger.info("tiktok_match_product: partial match — '%s'", norm_text)
            return StepResult.SUCCESS

    # No match found — signal coordinate fallback
    visible_names = [t for t, _ in candidates[:8]]
    logger.warning(
        "tiktok_match_product: no match for '%s'. Visible: %s — using coordinate fallback",
        target, visible_names,
    )
    step["_match_uia_failed"] = True
    return StepResult.SUCCESS


async def _attach_product(adb_address: str, step: dict) -> StepResult:
    """
    Tap the Add button associated with the matched product card.

    Uses bounds from _match_product step (step["_matched_bounds"]) to find
    the Add button in the same row/parent.  Falls back to first Add button
    near the top of results if no matched bounds are available.

    Does NOT verify attachment here — that is _verify_product's job.
    """
    product_name = step.get("product_name", "")
    matched_bounds = step.get("_matched_bounds", "")
    uia_failed = step.get("_match_uia_failed") or step.get("_search_uia_failed")

    # When UIAutomator failed on the results page, skip re-reading XML
    # and go straight to coordinate fallback — XML will be stale/empty anyway.
    if uia_failed and not matched_bounds:
        logger.info(
            "tiktok_attach_product: UIA failed flag set — "
            "tapping first product marketplace Add button via coordinates"
        )
        # First "Add" button in Product marketplace section:
        # display ≈ (580, 1220) at 900×2000 → physical ≈ (696, 1464) at 1080×2400
        # rx=0.644, ry=0.61 — first marketplace result's Add button
        await _run(adb_address, "shell", "input", "tap", "696", "1464")
        await asyncio.sleep(2.5)
        return StepResult.SUCCESS

    xml = await _ui_xml(adb_address)

    if matched_bounds:
        # Parse matched card bounds to find x/y centre
        bm = re.search(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', matched_bounds)
        if bm:
            card_x1, card_y1, card_x2, card_y2 = (
                int(bm.group(1)), int(bm.group(2)),
                int(bm.group(3)), int(bm.group(4)),
            )
            card_y_centre = (card_y1 + card_y2) // 2

            # Find the Add button whose vertical centre is closest to the card's
            best_add: tuple[int, int] | None = None
            best_dist = 9999
            for node_str in xml.split("<node "):
                is_add_btn = (
                    'text="Add"' in node_str
                    or 'content-desc="Add"' in node_str
                ) and 'clickable="true"' in node_str
                if not is_add_btn:
                    continue
                abm = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', node_str)
                if abm:
                    ax = (int(abm.group(1)) + int(abm.group(3))) // 2
                    ay = (int(abm.group(2)) + int(abm.group(4))) // 2
                    dist = abs(ay - card_y_centre)
                    if dist < best_dist:
                        best_dist = dist
                        best_add = (ax, ay)

            if best_add and best_dist < 300:
                await _run(adb_address, "shell", "input", "tap",
                           str(best_add[0]), str(best_add[1]))
                logger.info(
                    "tiktok_attach_product: tapped Add at %s (row dist=%dpx)",
                    best_add, best_dist,
                )
                await asyncio.sleep(2)
                # Handle optional confirmation
                await _tap_vision_button(
                    adb_address, step, "Add", "Confirm", "Done",
                    fallback_rx=0.85, fallback_ry=0.92,
                )
                await asyncio.sleep(1.5)
                return StepResult.SUCCESS

    # Fallback: vision button or first marketplace Add button (confirmed position)
    logger.warning("tiktok_attach_product: no matched bounds — using vision fallback")
    found = await _tap_vision_button(adb_address, step, "Add", "Confirm",
                                     fallback_rx=0.644, fallback_ry=0.61)
    await asyncio.sleep(2.5)
    return StepResult.SUCCESS if found else StepResult.RETRY


async def _verify_product(adb_address: str, step: dict) -> StepResult:
    """
    Verify the product is attached by checking the post-editor screen.

    At least one of these must be true:
      - Exact product name visible in XML or vision text
      - "Added", "Attached", "Linked" state visible
      - Add link button replaced by an attached-product card (product name in XML near
        a parent node that previously showed "Add link")

    On failure: returns RETRY (executor captures screenshot/XML for diagnostics).
    """
    product_name = step.get("product_name", "")
    target = _normalize(product_name) if product_name else ""

    await asyncio.sleep(1.5)  # wait for post editor to settle

    xml = await _ui_xml(adb_address)
    xml_lower = xml.lower()

    # Check 1: product name in XML
    if target and target in xml_lower:
        logger.info("tiktok_verify_product: confirmed via XML — product name visible")
        return StepResult.SUCCESS

    # Check 2: "added" / "linked" indicator
    if any(kw in xml_lower for kw in ("product added", "product linked", "added", "attached")):
        logger.info("tiktok_verify_product: confirmed via 'added' indicator in XML")
        return StepResult.SUCCESS

    # Check 3: Vision Engine
    analysis = await _vision(adb_address, step)
    if analysis:
        visible_lower = " ".join(t.lower() for t in analysis.visible_text)
        if target and target in visible_lower:
            logger.info("tiktok_verify_product: confirmed via vision text")
            return StepResult.SUCCESS
        if any(kw in visible_lower for kw in ("added", "linked", "attached")):
            logger.info("tiktok_verify_product: confirmed via vision 'added'")
            return StepResult.SUCCESS

    logger.warning(
        "tiktok_verify_product: product '%s' not confirmed — XML snippet: %s",
        product_name,
        xml_lower[:300],
    )
    return StepResult.RETRY


async def _pre_publish_check(adb_address: str, step: dict) -> StepResult:
    """
    Final screen check before the Publish button.

    In STOP_BEFORE_POST mode this is the last step.
    SUCCESS here causes executor → READY_FOR_REVIEW status.
    """
    analysis = await _vision(adb_address, step)
    if not analysis:
        return StepResult.SUCCESS  # Vision unavailable — proceed optimistically

    error_words = {"failed", "error", "not available", "try again"}
    visible = {t.lower() for t in analysis.visible_text}
    if error_words & visible:
        return StepResult.RETRY

    if not analysis.has_button("Post", "Publish", "Share now"):
        return StepResult.RETRY

    return StepResult.SUCCESS


async def _publish(adb_address: str, step: dict) -> StepResult:
    from app.apps.tiktok.constants import PUBLISH_DELAY
    post_type = step.get("post_type", "post_now")

    if post_type == "draft":
        found = await _tap_vision_button(
            adb_address, step, "Drafts", "Save draft",
            fallback_rx=0.15, fallback_ry=0.92,
        )
    else:
        found = await _tap_vision_button(
            adb_address, step, "Post", "Publish", "Share now",
            fallback_rx=0.85, fallback_ry=0.92,
        )

    await asyncio.sleep(PUBLISH_DELAY)
    return StepResult.SUCCESS if found else StepResult.RETRY


async def _verify_success(adb_address: str, step: dict) -> StepResult:
    from app.apps.tiktok.constants import VERIFY_TIMEOUT
    device_id = step.get("device_id", "")

    if device_id:
        try:
            from app.vision.analyzer import wait_until
            analysis = await wait_until(
                adb_address, device_id,
                button="View",
                timeout=VERIFY_TIMEOUT,
                poll_interval=2.0,
            )
            if analysis.has_button("View", "Share", "See your video", "Done"):
                return StepResult.SUCCESS
            visible = {t.lower() for t in analysis.visible_text}
            if "posted" in visible or "published" in visible or "uploaded" in visible:
                return StepResult.SUCCESS
            return StepResult.RETRY
        except Exception:
            pass
    await asyncio.sleep(5)
    return StepResult.SUCCESS


async def _first_comment(adb_address: str, step: dict) -> StepResult:
    comment = step.get("comment", "")
    if not comment:
        return StepResult.SKIP

    found = await _tap_vision_button(
        adb_address, step, "Add comment", "Comment",
        fallback_rx=0.5, fallback_ry=0.88,
    )
    if not found:
        return StepResult.SKIP

    await asyncio.sleep(0.5)
    await _clipboard_paste(adb_address, comment)
    await asyncio.sleep(0.3)
    await _tap_vision_button(
        adb_address, step, "Post", "Send", fallback_rx=0.85, fallback_ry=0.92
    )
    await asyncio.sleep(1)
    return StepResult.SUCCESS


# ── Handler registry ──────────────────────────────────────────────────────────

HANDLERS: dict = {
    "tiktok_launch":                _launch,
    "tiktok_verify_home":           _verify_home,
    "tiktok_push_video":            _push_video,
    "tiktok_open_upload":           _open_upload,
    "tiktok_select_video":          _select_video,
    "tiktok_verify_preview":        _verify_preview,
    "tiktok_tap_next":              _tap_next,
    "tiktok_advance_to_post_editor": _advance_to_post_editor,
    "tiktok_edit_cover":            _edit_cover,
    "tiktok_insert_caption":        _insert_caption,
    "tiktok_open_product_selector": _open_product_selector,
    "tiktok_wait_product_page":     _wait_product_page,
    "tiktok_search_product":        _search_product,
    "tiktok_match_product":         _match_product,
    "tiktok_attach_product":        _attach_product,
    "tiktok_verify_product":        _verify_product,
    "tiktok_pre_publish_check":     _pre_publish_check,
    "tiktok_publish":               _publish,
    "tiktok_verify_success":        _verify_success,
    "tiktok_first_comment":         _first_comment,
}
