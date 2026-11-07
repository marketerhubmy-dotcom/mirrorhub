"""
YouTube Create step handlers — MVP 0.2

Key changes vs 0.1:
  - _push_image: job-ID filename, mkdir, rm old mh_job files, verify via ls
  - _clipboard_paste: cmd clipboard set-text (Android 12+) + KEYCODE_PASTE
  - _type_safe: proper shell metachar escaping (no stripping of #, &, (, ))
  - _paste_prompt: uses _clipboard_paste instead of _type
  - _add_image: cleans dir first so top-left is always our image
  - _wait_generation: real polling — SUCCESS / FAILED / TIMEOUT distinguished
"""
import asyncio
import re
import subprocess
from pathlib import Path

from .state_machine import StepResult


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


# ── Text input ────────────────────────────────────────────────────────────────

def _shell_single_quote(text: str) -> str:
    """
    Wrap text in single quotes for safe passing to the Android device shell.
    Embedded single quotes use the '\'' escape sequence.
    """
    return "'" + text.replace("'", "'\\''") + "'"


async def _clipboard_paste(adb_address: str, text: str) -> None:
    """
    Set Android clipboard via 'cmd clipboard set-text' (Android 12+ / API 31+)
    then paste with KEYCODE_PASTE.

    Falls back to _type_safe() if the command is unavailable (older Android).

    Why prefer clipboard over input text:
      - Preserves Malay chars, emoji, #hashtags, &, (, ) without stripping
      - Atomic: entire text lands at once, no race with the IME
    """
    quoted = _shell_single_quote(text)
    result = await _run(adb_address, "shell", "cmd", "clipboard", "set-text", quoted)

    # cmd clipboard returns empty on success; any error message triggers fallback
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
    """
    Type text via adb shell input text with CORRECT shell metacharacter escaping.

    Does NOT strip content — escapes shell-special characters so the device
    shell delivers them faithfully.  Critical fix: # was previously unescaped,
    causing hashtags to be silently swallowed as shell comments.

    Spaces are encoded as %s (adb input text convention).
    Line breaks are sent as KEYCODE_ENTER.
    """
    ESCAPES = [
        ('\\', '\\\\'),
        ('"',  '\\"'),
        ("'",  "\\'"),
        ('$',  '\\$'),
        ('(',  '\\('),
        (')',  '\\)'),
        ('&',  '\\&'),
        ('|',  '\\|'),
        (';',  '\\;'),
        ('<',  '\\<'),
        ('>',  '\\>'),
        ('`',  '\\`'),
        ('!',  '\\!'),
        ('#',  '\\#'),
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


# ── Step handlers ─────────────────────────────────────────────────────────────

async def _push_image(adb_address: str, step: dict) -> StepResult:
    """
    Push the reference image to the device.

    MVP 0.2 changes:
      - Uses mh_job{job_id}.jpg — deterministic, not a shared filename
      - Deletes all previous mh_job*.jpg first so this image is the newest
      - Verifies push via ls before returning SUCCESS
      - Triggers media scanner and waits for it to register the file
    """
    job_id      = step.get("job_id", "0")
    local_path  = step["local"]
    device_dir  = step.get("device_dir", "/sdcard/DCIM/mirrorhub")
    filename    = step.get("device_filename", f"mh_job{job_id}.jpg")
    device_path = f"{device_dir}/{filename}"

    await _run(adb_address, "shell", "mkdir", "-p", device_dir)
    await _run(adb_address, "shell", "rm", "-f", f"{device_dir}/mh_job*.jpg")

    proc = await asyncio.create_subprocess_exec(
        str(_adb()), "-s", adb_address,
        "push", local_path, device_path,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    _, err = await proc.communicate()
    if proc.returncode != 0:
        return StepResult.RETRY

    ls_out = await _run(adb_address, "shell", "ls", "-la", device_path)
    if "No such file" in ls_out or filename not in ls_out:
        return StepResult.RETRY

    await _run(adb_address, "shell", "am", "broadcast",
               "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE",
               "-d", f"file://{device_path}")
    await asyncio.sleep(2)
    step["_device_path"] = device_path
    return StepResult.SUCCESS


async def _launch(adb_address: str, step: dict) -> StepResult:
    # Force-stop first so YTC always starts fresh on its home screen.
    # Without this, am start-activity restores the last open project,
    # causing _new_project to tap the wrong screen.
    await _run(adb_address, "shell", "am", "force-stop",
               "com.google.android.apps.youtube.producer")
    await asyncio.sleep(1)
    await _run(
        adb_address, "shell", "am", "start-activity", "-W",
        "-n", "com.google.android.apps.youtube.producer/.application.MainActivity",
    )
    await asyncio.sleep(5)
    return StepResult.SUCCESS


async def _new_project(adb_address: str, step: dict) -> StepResult:
    # Tap "Create Project" at bottom nav (content-desc "Create Project", y≈2196)
    found = await _tap_vision_button(
        adb_address, step, "Create Project",
        fallback_rx=0.5, fallback_ry=0.915,
    )
    if not found:
        return StepResult.RETRY
    await asyncio.sleep(2)

    # Tap "Generate video" on the project type screen
    found = await _tap_vision_button(
        adb_address, step, "Generate video",
        fallback_rx=0.254, fallback_ry=0.230,  # (274/1080, 553/2400)
    )
    if not found:
        return StepResult.RETRY
    await asyncio.sleep(2)
    return StepResult.SUCCESS


async def _select_script(adb_address: str, step: dict) -> StepResult:
    # This screen does not exist in the YouTube Create video-generation flow
    return StepResult.SKIP


async def _paste_prompt(adb_address: str, step: dict) -> StepResult:
    """
    Type the video prompt into the YTC text field.

    Uses _type_safe directly — cmd clipboard set-text is not available on
    Android 17 Pixel 6 ("No shell command implementation."), so input text
    with %s for spaces is the reliable path.

    Non-ASCII characters (e.g. curly quotes â€œ/â€ from AI text stored with
    encoding corruption) must be stripped before typing.  adb shell input text
    receives them as an incomplete UTF-8 byte sequence and fails the ENTIRE
    command silently, leaving the text field empty.
    """
    raw = step["script"]
    # Strip non-ASCII: keeps the text readable while preventing ADB failure
    script = raw.encode("ascii", errors="ignore").decode("ascii").strip()
    if not script:
        return StepResult.SUCCESS

    # Tap the text area to ensure it has focus
    await _run(adb_address, "shell", "input", "tap", "540", "400")
    await asyncio.sleep(0.5)

    # Clear any existing content
    await _run(adb_address, "shell", "input", "keyevent", "KEYCODE_CTRL_A")
    await asyncio.sleep(0.2)
    await _run(adb_address, "shell", "input", "keyevent", "KEYCODE_DEL")
    await asyncio.sleep(0.2)

    await _type_safe(adb_address, script)
    await asyncio.sleep(1)
    return StepResult.SUCCESS


async def _add_image(adb_address: str, step: dict) -> StepResult:
    """
    Attach the reference image via YTC's 'Upload ingredients' → mirrorhub album flow.

    Handles both the legacy in-app gallery (Gallery ▼ dropdown) and the Android
    13+ system photo picker (Photos / Collections tabs).

    Key fixes vs previous version:
    - Dismisses the 'Choose a cloud media app' one-time system dialog that
      appears on first use and blocks the Add button.
    - Uses 'Collections' tab (system picker) as well as 'Gallery ▼' (legacy).
    - Verifies the picker actually closed; retries if still visible.
    - Fallback Add button at ry=0.88 (y≈2112) — above nav bar, not ON it.
    """
    # Dismiss keyboard — tap below content card; harmless if not showing
    await _run(adb_address, "shell", "input", "tap", "540", "1100")
    await asyncio.sleep(0.5)

    # Open ingredients picker.
    # Fallback ry=0.35 ≈ y=840 — image-attachment area of the content card.
    found = await _tap_vision_button(
        adb_address, step,
        "Upload up to 3 ingredients", "Upload ingredients", "Upload",
        fallback_rx=0.5, fallback_ry=0.35,
    )
    if not found:
        return StepResult.RETRY
    await asyncio.sleep(2)

    # Dismiss 'Choose a cloud media app' dialog if it appeared.
    # This one-time system dialog blocks the grid and the Add/Done button.
    await _run(adb_address, "shell", "uiautomator", "dump", "/sdcard/mh_ui.xml")
    xml = await _run(adb_address, "shell", "cat", "/sdcard/mh_ui.xml")
    if "cloud" in xml.lower() or "backed up" in xml.lower():
        for node_str in xml.split("<node "):
            if 'text="Dismiss"' in node_str:
                m = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', node_str)
                if m:
                    dx = (int(m.group(1)) + int(m.group(3))) // 2
                    dy = (int(m.group(2)) + int(m.group(4))) // 2
                    await _run(adb_address, "shell", "input", "tap", str(dx), str(dy))
                    break
        await asyncio.sleep(0.5)

    # Switch to Collections/Albums view.
    # System photo picker: 'Collections' tab.  Legacy in-app picker: 'Gallery ▼'.
    await _tap_vision_button(
        adb_address, step, "Collections", "Albums", "Gallery ▼", "Gallery",
        fallback_rx=0.5, fallback_ry=0.30,  # right-side tab in system picker
    )
    await asyncio.sleep(1)

    # Find and tap the mirrorhub album
    await _run(adb_address, "shell", "uiautomator", "dump", "/sdcard/mh_ui.xml")
    xml = await _run(adb_address, "shell", "cat", "/sdcard/mh_ui.xml")
    tapped_album = False
    for node_str in xml.split("<node "):
        if "mirrorhub" in node_str.lower():
            m = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', node_str)
            if m:
                x = (int(m.group(1)) + int(m.group(3))) // 2
                y = (int(m.group(2)) + int(m.group(4))) // 2
                await _run(adb_address, "shell", "input", "tap", str(x), str(y))
                tapped_album = True
                break
    if not tapped_album:
        return StepResult.RETRY
    await asyncio.sleep(1.5)

    # Tap image thumbnail(s) in the album (hardcoded grid, 1080x2400, 3 columns).
    # count=1 (default): only the top-left thumbnail — confirmed working position.
    # count=2+: also tap subsequent thumbnails (product image is pushed first via
    # _push_image so it always lands top-left; extra images — e.g. a user-supplied
    # avatar reference — follow via _push_image_file, so this order is deterministic).
    # NOTE: positions beyond the first are an estimate (same 3-col ratio as the
    # ytcreate_add_images grid) and have not been confirmed on-device yet.
    count = max(1, int(step.get("count", 1)))
    THUMB_GRID = [(198, 646), (540, 646), (882, 646)]
    for x, y in THUMB_GRID[:count]:
        await _run(adb_address, "shell", "input", "tap", str(x), str(y))
        await asyncio.sleep(0.5)

    # Confirm selection.
    # System picker uses 'Add'; legacy picker uses 'Done'.
    # Fallback ry=0.88 ≈ y=2112 — just above the navigation bar.
    await _tap_vision_button(
        adb_address, step, "Add", "Done",
        fallback_rx=0.5, fallback_ry=0.88,
    )
    await asyncio.sleep(1.5)

    # Verify the picker closed — if Photos+Collections tabs still visible,
    # the Add tap missed and we need to retry.
    await _run(adb_address, "shell", "uiautomator", "dump", "/sdcard/mh_ui.xml")
    xml = await _run(adb_address, "shell", "cat", "/sdcard/mh_ui.xml")
    if 'text="Photos"' in xml and 'text="Collections"' in xml:
        # One more attempt with alternate button position (top-right)
        await _tap_vision_button(adb_address, step, "Add", "Done",
                                 fallback_rx=0.88, fallback_ry=0.06)
        await asyncio.sleep(1)
        await _run(adb_address, "shell", "uiautomator", "dump", "/sdcard/mh_ui.xml")
        xml = await _run(adb_address, "shell", "cat", "/sdcard/mh_ui.xml")
        if 'text="Photos"' in xml and 'text="Collections"' in xml:
            return StepResult.RETRY
    return StepResult.SUCCESS


async def _generate(adb_address: str, step: dict) -> StepResult:
    # Dismiss software keyboard first so the Generate button is at its true position
    await _run(adb_address, "shell", "input", "tap", "540", "900")
    await asyncio.sleep(1)

    found = await _tap_vision_button(
        adb_address, step, "Generate",
        fallback_rx=0.5, fallback_ry=0.55,
    )
    if not found:
        return StepResult.RETRY
    await asyncio.sleep(5)
    return StepResult.SUCCESS


async def _wait_generation(adb_address: str, step: dict) -> StepResult:
    """
    Poll until YouTube Create video generation completes.

    Outcomes:
      SUCCESS — "Continue", "Export", "Done", or "Share" button detected
      ABORT   — unrecoverable error OR timeout exceeded

    When YTC shows "Something went wrong, please try again." the function taps
    "Try again" (up to 2 times) and continues polling instead of ABORTing
    immediately — these failures are typically transient server-side errors.
    """
    wait_sec      = int(step.get("wait_seconds", 120))
    poll_interval = float(step.get("poll_interval", 8.0))
    device_id     = step.get("device_id", "")

    SUCCESS_BUTTONS  = ("Continue", "Export", "Done", "Next", "Share", "Use video", "Use Video")
    # "try again" removed — it's a recovery button, not a failure word
    FATAL_WORDS      = ("error", "failed", "couldn't", "something went wrong")
    MAX_RECOVERIES   = 2
    recoveries       = 0

    loop     = asyncio.get_running_loop()
    deadline = loop.time() + wait_sec

    while loop.time() < deadline:
        await asyncio.sleep(poll_interval)

        if device_id:
            try:
                from app.vision.analyzer import analyze_screen
                analysis = await analyze_screen(adb_address, device_id)
                if analysis.has_button(*SUCCESS_BUTTONS):
                    return StepResult.SUCCESS
                visible_lower = " ".join(t.lower() for t in analysis.visible_text)
                if any(e in visible_lower for e in FATAL_WORDS):
                    if recoveries < MAX_RECOVERIES and analysis.has_button("Try again"):
                        await _tap_vision_button(
                            adb_address, step, "Try again",
                            fallback_rx=0.5, fallback_ry=0.88,
                        )
                        recoveries += 1
                        await asyncio.sleep(5)
                        continue
                    return StepResult.ABORT
                continue
            except Exception:
                pass

        await _run(adb_address, "shell", "uiautomator", "dump", "/sdcard/mh_ui.xml")
        xml = await _run(adb_address, "shell", "cat", "/sdcard/mh_ui.xml")
        for btn in SUCCESS_BUTTONS:
            # YTC uses content-desc (Flutter); also check text= for safety
            if re.search(
                rf'(?:text|content-desc)="{re.escape(btn)}"', xml, re.IGNORECASE
            ):
                return StepResult.SUCCESS
        xml_lower = xml.lower()
        if any(e in xml_lower for e in FATAL_WORDS):
            if recoveries < MAX_RECOVERIES:
                tapped = False
                for node_str in xml.split("<node "):
                    if 'try again' in node_str.lower():
                        m = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', node_str)
                        if m:
                            x = (int(m.group(1)) + int(m.group(3))) // 2
                            y = (int(m.group(2)) + int(m.group(4))) // 2
                            await _run(adb_address, "shell", "input", "tap", str(x), str(y))
                            tapped = True
                            recoveries += 1
                            await asyncio.sleep(5)
                            break
                if tapped:
                    continue
            return StepResult.ABORT

    # Timeout
    return StepResult.ABORT


async def _export(adb_address: str, step: dict) -> StepResult:
    """
    Full export sequence after generation completes:
    1. Tap 'Use video' (generation completion button)
    2. Tap 'Export' in the project editor (top-right)
    3. Tap the clickable Export button in the export settings sheet
    4. Wait for video render (~8s)
    5. Tap 'Share…' on the 'Upload to YouTube' success screen
    → returns SUCCESS with the Android share sheet open
    """
    # Step 1: Tap "Use video"
    found = await _tap_vision_button(
        adb_address, step, "Use video", "Use Video",
        fallback_rx=0.5, fallback_ry=0.88,
    )
    if not found:
        return StepResult.RETRY
    await asyncio.sleep(2)

    # Step 2: Project editor — tap Export at top-right (content-desc "Export")
    found = await _tap_vision_button(
        adb_address, step, "Export",
        fallback_rx=0.942, fallback_ry=0.141,  # (1017/1080, 338/2400)
    )
    if not found:
        return StepResult.RETRY
    await asyncio.sleep(1.5)

    # Step 3: Export settings sheet — tap the android.widget.Button Export (not the title View)
    await _run(adb_address, "shell", "uiautomator", "dump", "/sdcard/mh_ui.xml")
    xml = await _run(adb_address, "shell", "cat", "/sdcard/mh_ui.xml")
    tapped = False
    for node_str in xml.split("<node "):
        if 'content-desc="Export"' in node_str and 'clickable="true"' in node_str:
            m = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', node_str)
            if m:
                x = (int(m.group(1)) + int(m.group(3))) // 2
                y = (int(m.group(2)) + int(m.group(4))) // 2
                await _run(adb_address, "shell", "input", "tap", str(x), str(y))
                tapped = True
                break
    if not tapped:
        await _run(adb_address, "shell", "input", "tap", "540", "2295")

    await asyncio.sleep(8)  # Wait for video render + device save

    # Step 4: "Upload to YouTube" screen — tap "Share…"
    found = await _tap_vision_button(
        adb_address, step, "Share…", "Share...", "Share",
        fallback_rx=0.5, fallback_ry=0.979,
    )
    if not found:
        return StepResult.RETRY
    await asyncio.sleep(2)
    return StepResult.SUCCESS


async def _share(adb_address: str, step: dict) -> StepResult:
    """
    Android share sheet → TikTok → 'Video' → dismiss location dialog → tap Next.
    After SUCCESS the device is on the TikTok post-details screen.
    """
    step["handoff_method"] = "share_sheet"

    # Step 1: Find TikTok in the share sheet
    await _run(adb_address, "shell", "uiautomator", "dump", "/sdcard/mh_ui.xml")
    xml = await _run(adb_address, "shell", "cat", "/sdcard/mh_ui.xml")
    m = re.search(
        r'text="TikTok"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
        xml, re.IGNORECASE,
    )
    if not m:
        return StepResult.RETRY
    x = (int(m.group(1)) + int(m.group(3))) // 2
    y = (int(m.group(2)) + int(m.group(4))) // 2
    await _run(adb_address, "shell", "input", "tap", str(x), str(y))
    await asyncio.sleep(3)

    # Step 2: "Share on TikTok" dialog — tap "Video"
    found = await _tap_vision_button(
        adb_address, step, "Video",
        fallback_rx=0.286, fallback_ry=0.804,  # (309/1080, 1929/2400)
    )
    if not found:
        return StepResult.RETRY
    await asyncio.sleep(5)

    # Step 3: Dismiss location permission dialog if present
    await _run(adb_address, "shell", "uiautomator", "dump", "/sdcard/mh_ui.xml")
    xml = await _run(adb_address, "shell", "cat", "/sdcard/mh_ui.xml")
    if "precise location" in xml.lower():
        for node_str in xml.split("<node "):
            if 'text="Allow"' in node_str and 'clickable="true"' in node_str:
                m2 = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', node_str)
                if m2:
                    x2 = (int(m2.group(1)) + int(m2.group(3))) // 2
                    y2 = (int(m2.group(2)) + int(m2.group(4))) // 2
                    await _run(adb_address, "shell", "input", "tap", str(x2), str(y2))
                    await asyncio.sleep(1)
                    break

    # Step 4: Tap "Next" to reach the TikTok post-details screen
    found = await _tap_vision_button(
        adb_address, step, "Next",
        fallback_rx=0.737, fallback_ry=0.909,  # (796/1080, 2181/2400)
    )
    if not found:
        return StepResult.RETRY
    await asyncio.sleep(4)
    return StepResult.SUCCESS


async def _post(adb_address: str, step: dict) -> StepResult:
    await _tap_vision_button(
        adb_address, step, "Next", fallback_rx=0.85, fallback_ry=0.07
    )
    await asyncio.sleep(3)
    post_type = step.get("post_type", "draft")
    if post_type == "post_now":
        await _tap_vision_button(
            adb_address, step, "Post", fallback_rx=0.85, fallback_ry=0.92
        )
    elif post_type == "draft":
        await _tap_vision_button(
            adb_address, step, "Drafts", fallback_rx=0.15, fallback_ry=0.92
        )
    elif post_type == "schedule":
        await _tap_vision_button(
            adb_address, step, "Schedule", fallback_rx=0.5, fallback_ry=0.78
        )
        await asyncio.sleep(1)
        await _tap_vision_button(
            adb_address, step, "Confirm", fallback_rx=0.85, fallback_ry=0.92
        )
    await asyncio.sleep(2)
    return StepResult.SUCCESS


# ── Extended handlers (kept for workflow_builder compatibility) ───────────────

async def _push_image_file(adb_address: str, step: dict) -> StepResult:
    device_dir  = step.get("device_dir", "/sdcard/DCIM/mirrorhub")
    filename    = step.get("device_filename", "mh_image_00.jpg")
    device_path = f"{device_dir}/{filename}"
    await _run(adb_address, "shell", "mkdir", "-p", device_dir)
    cleanup_pattern = step.get("cleanup_pattern", "")
    if cleanup_pattern:
        await _run(adb_address, "shell", "rm", "-f", f"{device_dir}/{cleanup_pattern}")
    proc = await asyncio.create_subprocess_exec(
        str(_adb()), "-s", adb_address,
        "push", step["local"], device_path,
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
    return StepResult.SUCCESS


async def _add_images(adb_address: str, step: dict) -> StepResult:
    count = max(1, int(step.get("count", 1)))
    await _tap_vision_button(
        adb_address, step, "Media", fallback_rx=0.15, fallback_ry=0.85
    )
    await asyncio.sleep(1)
    await _tap_vision_button(
        adb_address, step, "Gallery", fallback_rx=0.25, fallback_ry=0.45
    )
    await asyncio.sleep(2)
    grid = [
        (0.15, 0.25), (0.50, 0.25), (0.85, 0.25),
        (0.15, 0.45), (0.50, 0.45), (0.85, 0.45),
        (0.15, 0.65), (0.50, 0.65), (0.85, 0.65),
        (0.15, 0.85),
    ]
    for rx, ry in grid[:count]:
        await _tap_rel(adb_address, rx, ry)
        await asyncio.sleep(0.4)
    await _tap_vision_button(
        adb_address, step, "Add", fallback_rx=0.85, fallback_ry=0.92
    )
    await asyncio.sleep(1)
    return StepResult.SUCCESS


async def _select_resolution(adb_address: str, step: dict) -> StepResult:
    resolution = step.get("resolution", "1080p")
    found = await _tap_vision_button(adb_address, step, resolution, "1080p", "HD")
    if not found:
        return StepResult.SKIP
    await asyncio.sleep(0.5)
    return StepResult.SUCCESS


# ── Handler registry ──────────────────────────────────────────────────────────

HANDLERS: dict = {
    "ytcreate_push_image":        _push_image,
    "ytcreate_launch":            _launch,
    "ytcreate_new_project":       _new_project,
    "ytcreate_select_script":     _select_script,
    "ytcreate_paste_prompt":      _paste_prompt,
    "ytcreate_add_image":         _add_image,
    "ytcreate_generate":          _generate,
    "ytcreate_wait_generation":   _wait_generation,
    "ytcreate_export":            _export,
    "ytcreate_share":             _share,
    "ytcreate_post":              _post,
    "ytcreate_push_image_file":   _push_image_file,
    "ytcreate_add_images":        _add_images,
    "ytcreate_select_resolution": _select_resolution,
}
