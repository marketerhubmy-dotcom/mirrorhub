"""
Main Vision Engine entry point.

Public API:
    analyze_screen(adb_address, device_id, provider="uiautomator") -> ScreenAnalysis
    wait_until(adb_address, device_id, *, screen, button, loading, timeout) -> ScreenAnalysis

Every call:
  1. Captures screenshot
  2. Runs provider analysis
  3. Caches result
  4. Broadcasts via WebSocket
  5. Returns ScreenAnalysis
"""
import asyncio
import json
from datetime import datetime, timezone

from app.websocket.manager import manager
from .screenshot import capture
from .providers import get_provider
from .cache import put, get as get_cached
from .state import ScreenAnalysis


async def _broadcast(analysis: ScreenAnalysis) -> None:
    data = json.dumps({"type": "vision_state", "payload": analysis.to_dict()})
    await manager.broadcast_vision(analysis.device_id, data)


async def analyze_screen(
    adb_address: str,
    device_id: str,
    provider: str = "uiautomator",
    use_cache_ms: int = 0,
) -> ScreenAnalysis:
    """
    Full vision pipeline: screenshot → OCR/AI → classify → cache → broadcast.

    Args:
        use_cache_ms: if > 0, return cached result if it's fresher than this many ms.
    """
    if use_cache_ms > 0:
        cached = get_cached(device_id)
        if cached:
            age_ms = (datetime.now(timezone.utc) - cached.timestamp).total_seconds() * 1000
            if age_ms < use_cache_ms:
                return cached

    cap = await capture(adb_address, device_id)
    p = get_provider(provider)
    analysis = await p.analyze(adb_address, device_id, cap.data)

    analysis.screenshot_path = cap.web_path
    analysis.width = cap.width
    analysis.height = cap.height
    analysis.timestamp = cap.timestamp

    put(device_id, analysis)
    await _broadcast(analysis)
    return analysis


async def wait_until(
    adb_address: str,
    device_id: str,
    *,
    screen: str | None = None,
    button: str | None = None,
    loading: bool | None = None,
    timeout: int = 30,
    poll_interval: float = 3.0,
    provider: str = "uiautomator",
) -> ScreenAnalysis:
    """
    Poll until the specified conditions are satisfied.
    Returns the last ScreenAnalysis regardless of whether conditions were met.

    Example:
        analysis = await wait_until(
            adb_address, device_id,
            button="Continue",
            loading=False,
            timeout=90,
        )
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    last = await analyze_screen(adb_address, device_id, provider=provider)

    while loop.time() < deadline:
        ok = True

        if screen:
            screen_lower = screen.lower()
            if (
                last.screen_name.lower() != screen_lower
                and last.screen_type.value.lower() != screen_lower
            ):
                ok = False

        if button and not last.has_button(button):
            ok = False

        if loading is not None and last.loading != loading:
            ok = False

        if ok:
            return last

        await asyncio.sleep(poll_interval)
        last = await analyze_screen(adb_address, device_id, provider=provider)

    return last
