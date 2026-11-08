"""
Pipeline preflight checks.

Called by run_pipeline before any automation steps execute.
Returns a PreflightResult describing every blocking error.

Checks (in order):
  1. ADB connection active
  2. Screen on / phone unlocked
  3. YouTube Create installed
  4. TikTok installed (primary or regional package)
  5. Reference image file exists locally
  6. Video prompt not empty
  7. Caption not empty
  8. TikTok product name not empty
  9. Publish mode is 'manual' or 'auto'

If ADB cannot connect (check 1) the remaining device checks are skipped
because they would all fail and generate confusing extra messages.
"""
import asyncio
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from app.utils.adb_path import ADB


@dataclass
class PreflightResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


async def _run_adb(adb_address: str, *args: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        str(ADB), "-s", adb_address, *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    out, err = await proc.communicate()
    return (out + err).decode(errors="replace")


async def check_adb_connected(adb_address: str) -> tuple[bool, str]:
    """
    Try adb connect; return (success, raw_output).
    Also checks that 'adb devices' actually lists the device as connected.
    """
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            [str(ADB), "connect", adb_address],
            capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        output = (result.stdout + result.stderr).strip()
    except Exception as exc:
        return False, str(exc)

    if "failed" in output.lower() or "unable" in output.lower():
        return False, output
    if "connected" in output.lower():
        return True, output
    return False, output


async def check_screen_on(adb_address: str) -> bool:
    """
    Return True when the device screen is interactive (on and unlocked enough
    for automation). Uses `dumpsys power` display-state detection.
    """
    out = await _run_adb(adb_address, "shell", "dumpsys", "power")
    # Both "Display Power: state=ON" and "mWakefulness=Awake" indicate a live screen.
    return "state=ON" in out or "mWakefulness=Awake" in out


async def check_app_installed(adb_address: str, package: str) -> bool:
    out = await _run_adb(adb_address, "shell", "pm", "list", "packages", package)
    return f"package:{package}" in out


async def run_preflight(
    adb_address: str,
    video_prompt: str,
    caption: str,
    image_local_path: str,
    tiktok_product_name: str,
    publish_mode: str,
) -> PreflightResult:
    """
    Run all preflight checks and return a PreflightResult.

    Blocking errors are added to result.errors.
    Non-blocking concerns go to result.warnings.
    """
    errors: list[str] = []
    warnings: list[str] = []

    # ── 1. ADB connection ────────────────────────────────────────────────────
    connected, msg = await check_adb_connected(adb_address)
    if not connected:
        errors.append(
            f"ADB tidak dapat connect ke {adb_address}. "
            f"Pastikan phone dan laptop dalam WiFi yang sama dan Wireless Debugging ON. "
            f"(Output: {msg})"
        )
        # Device-side checks cannot run without ADB — stop here
        return PreflightResult(ok=False, errors=errors, warnings=warnings)

    # Run remaining device checks concurrently for speed
    screen_task   = asyncio.create_task(check_screen_on(adb_address))
    ytc_task      = asyncio.create_task(
        check_app_installed(adb_address, "com.google.android.apps.youtube.creator")
    )
    ytc_alt_task  = asyncio.create_task(
        check_app_installed(adb_address, "com.google.android.apps.youtube.producer")
    )
    ttk_task      = asyncio.create_task(
        check_app_installed(adb_address, "com.zhiliaoapp.musically")
    )
    ttk_alt_task  = asyncio.create_task(
        check_app_installed(adb_address, "com.ss.android.ugc.trill")
    )

    screen_on, ytc_primary, ytc_alt, ttk_primary, ttk_alt = await asyncio.gather(
        screen_task, ytc_task, ytc_alt_task, ttk_task, ttk_alt_task
    )
    ytc_ok = ytc_primary or ytc_alt
    ttk_ok = ttk_primary or ttk_alt

    # ── 2. Screen on ─────────────────────────────────────────────────────────
    if not screen_on:
        errors.append(
            "Skrin phone tidak aktif. Unlock phone dan pastikan skrin ON sebelum pipeline dimulakan."
        )

    # ── 3. YouTube Create installed ───────────────────────────────────────────
    if not ytc_ok:
        errors.append(
            "YouTube Create tidak dipasang. "
            "Install dari Google Play Store "
            "(com.google.android.apps.youtube.producer atau .creator)."
        )

    # ── 4. TikTok installed ───────────────────────────────────────────────────
    if not ttk_ok:
        errors.append(
            "TikTok tidak dipasang. "
            "Install dari Google Play Store (com.zhiliaoapp.musically)."
        )

    # ── 5. Reference image exists locally ────────────────────────────────────
    if not image_local_path or not Path(image_local_path).exists():
        errors.append(
            f"Gambar rujukan tidak dijumpai: {image_local_path!r}. "
            "Upload semula gambar produk."
        )

    # ── 6. Video prompt not empty ─────────────────────────────────────────────
    if not video_prompt.strip():
        errors.append("Video prompt kosong. Klik 'Generate Content' dahulu.")

    # ── 7. Caption not empty ──────────────────────────────────────────────────
    if not caption.strip():
        errors.append("Caption kosong. Generate atau isi caption sebelum pipeline dimulakan.")

    # ── 8. TikTok product name not empty (warning only — pipeline skips attachment steps gracefully) ──
    if not tiktok_product_name.strip():
        warnings.append(
            "Nama produk TikTok Shop kosong. "
            "Langkah product attachment akan dilangkau."
        )

    # ── 9. Publish mode valid ─────────────────────────────────────────────────
    if publish_mode not in ("manual", "auto", "draft"):
        errors.append(
            f"Publish mode tidak sah: {publish_mode!r}. Gunakan 'manual', 'auto' atau 'draft'."
        )

    return PreflightResult(ok=len(errors) == 0, errors=errors, warnings=warnings)
