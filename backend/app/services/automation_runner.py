import asyncio
import re
import subprocess
from pathlib import Path

from app.services import adb_control
from app.services.device_ops import validate_package
from app.utils.adb_path import ADB

_runners: dict[str, "AutomationRunner"] = {}


class AutomationRunner:
    def __init__(self, device_id: str, adb_address: str):
        self.device_id = device_id
        self.adb_address = adb_address
        self.running = False
        self.logs: list[dict] = []
        self._screen_size: tuple[int, int] | None = None

    def _log(self, msg: str, status: str = "info") -> None:
        self.logs.append({"message": msg, "status": status})

    async def _adb_run(self, *args: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            str(ADB), "-s", self.adb_address, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        out, _ = await proc.communicate()
        return out.decode(errors="replace")

    async def _screen_size_px(self) -> tuple[int, int]:
        if self._screen_size:
            return self._screen_size
        raw = await self._adb_run("shell", "wm", "size")
        try:
            part = raw.strip().split(":")[-1].strip()
            w, h = part.split("x")
            self._screen_size = (int(w), int(h))
        except Exception:
            self._screen_size = (1080, 2400)
        return self._screen_size

    async def _tap(self, rx: float, ry: float) -> None:
        w, h = await self._screen_size_px()
        await self._adb_run("shell", "input", "tap", str(int(rx * w)), str(int(ry * h)))

    async def _tap_text(self, text: str, fallback: list[float] | None = None) -> bool:
        """Find UI element by text via uiautomator dump, then tap it."""
        await self._adb_run("shell", "uiautomator", "dump", "/sdcard/mh_ui.xml")
        xml = await self._adb_run("shell", "cat", "/sdcard/mh_ui.xml")

        patterns = [
            rf'text="{re.escape(text)}"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
            rf'content-desc="{re.escape(text)}"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
        ]
        for pat in patterns:
            m = re.search(pat, xml, re.IGNORECASE)
            if m:
                x = (int(m.group(1)) + int(m.group(3))) // 2
                y = (int(m.group(2)) + int(m.group(4))) // 2
                await self._adb_run("shell", "input", "tap", str(x), str(y))
                return True

        if fallback:
            await self._tap(fallback[0], fallback[1])
            return True
        return False

    async def _type_text(self, text: str) -> None:
        """Type text line by line into the focused field.

        Goes through adb_control.input_text (validated + POSIX-quoted); the previous implementation passed
        unquoted text to `adb shell input text`, so characters such as ; | * ~ were interpreted by the phone's shell.
        """
        for line in text.splitlines() or [""]:
            for start in range(0, len(line), 400):                    # validate_text caps one call at 500 chars
                chunk = line[start:start + 400]
                if chunk.strip():
                    await asyncio.to_thread(adb_control.input_text, self.adb_address, chunk)
            await asyncio.to_thread(adb_control.keyevent, self.adb_address, "KEYCODE_ENTER")
            await asyncio.sleep(0.1)

    async def _run_step(self, step: dict) -> None:
        t = step["type"]

        if t == "open_app":
            await self._adb_run(
                "shell", "monkey", "-p", validate_package(step["package"]),
                "-c", "android.intent.category.LAUNCHER", "1",
            )

        elif t == "wait":
            await asyncio.sleep(float(step["seconds"]))

        elif t == "tap_rel":
            await self._tap(step["x"], step["y"])

        elif t == "tap_text":
            await self._tap_text(step["text"], step.get("fallback"))

        elif t == "type_text":
            await self._type_text(step["text"])

        elif t == "key":
            await asyncio.to_thread(adb_control.keyevent, self.adb_address, step["code"])

        elif t == "swipe_rel":
            w, h = await self._screen_size_px()
            x1, y1 = int(step["x1"] * w), int(step["y1"] * h)
            x2, y2 = int(step["x2"] * w), int(step["y2"] * h)
            ms = step.get("ms", 300)
            await self._adb_run("shell", "input", "swipe",
                                 str(x1), str(y1), str(x2), str(y2), str(ms))

        elif t == "push_file":
            proc = await asyncio.create_subprocess_exec(
                str(ADB), "-s", self.adb_address,
                "push", step["local"], step["remote"],
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            await proc.communicate()
            # Rescan media store so gallery picks it up
            await self._adb_run(
                "shell", "am", "broadcast",
                "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE",
                "-d", f"file://{step['remote']}",
            )

        elif t == "paste":
            await self._adb_run("shell", "input", "keyevent", "KEYCODE_CTRL_LEFT")
            await asyncio.sleep(0.05)
            await self._adb_run("shell", "input", "keyevent", "KEYCODE_V")

        elif t == "select_all":
            await self._adb_run("shell", "input", "keyevent", "KEYCODE_CTRL_LEFT")
            await asyncio.sleep(0.05)
            await self._adb_run("shell", "input", "keyevent", "KEYCODE_A")

    async def execute(self, steps: list[dict]) -> None:
        self.running = True
        self.logs = []
        try:
            for step in steps:
                if not self.running:
                    self._log("Automation dihentikan.", "stopped")
                    break
                label = step.get("label", step["type"])
                self._log(f"▶ {label}")
                await self._run_step(step)
                self._log(f"✓ {label}", "success")
                await asyncio.sleep(0.3)
        except Exception as e:
            self._log(f"❌ Error: {e}", "error")
        finally:
            self.running = False

    def stop(self) -> None:
        self.running = False


def get_runner(device_id: str) -> AutomationRunner | None:
    return _runners.get(device_id)


async def start(device_id: str, adb_address: str, steps: list[dict]) -> AutomationRunner:
    runner = AutomationRunner(device_id, adb_address)
    _runners[device_id] = runner
    asyncio.get_event_loop().create_task(runner.execute(steps))
    return runner


def stop(device_id: str) -> None:
    runner = _runners.get(device_id)
    if runner:
        runner.stop()


def build_chatgpt_steps(topic: str, chatgpt_wait: int = 30) -> list[dict]:
    """Steps untuk buka ChatGPT app, hantar prompt, dan copy response ke clipboard.
    `topic` boleh jadi topik biasa ATAU custom prompt yang dah lengkap."""
    # Kalau topic nampak macam custom prompt (multiline atau ada 'prompt' keyword), guna terus
    is_custom = "\n" in topic or len(topic) > 120
    prompt = topic if is_custom else (
        f"Jana script video TikTok 30-45 saat untuk promosi produk ini: {topic}. "
        "Bahasa Malaysia, ada hook menarik, tunjuk faedah produk, dan CTA. "
        "Script teks sahaja, terus cakap, tiada label atau timestamp."
    )
    return [
        {"type": "open_app", "package": "com.openai.chatgpt",
         "label": "Buka ChatGPT app"},
        {"type": "wait", "seconds": 3, "label": "Tunggu ChatGPT load"},

        # Tap new chat
        {"type": "tap_text", "text": "New chat", "fallback": [0.93, 0.12],
         "label": "New chat"},
        {"type": "wait", "seconds": 1},

        # Tap message input
        {"type": "tap_text", "text": "Message", "fallback": [0.5, 0.92],
         "label": "Tap message input"},
        {"type": "wait", "seconds": 0.5},

        # Type prompt
        {"type": "type_text", "text": prompt, "label": "Taip prompt ke ChatGPT"},
        {"type": "wait", "seconds": 0.5},

        # Send
        {"type": "tap_rel", "x": 0.93, "y": 0.92, "label": "Send prompt"},

        # Wait for response
        {"type": "wait", "seconds": chatgpt_wait,
         "label": f"Tunggu ChatGPT generate ({chatgpt_wait} saat)"},

        # Copy response — ChatGPT ada copy button bawah setiap response
        {"type": "tap_text", "text": "Copy", "fallback": [0.12, 0.72],
         "label": "Copy response ChatGPT"},
        {"type": "wait", "seconds": 1},
    ]


def build_workflow(
    script: str,
    image_local_path: str,
    post_type: str,
    schedule_time: str | None = None,
    use_clipboard: bool = False,
) -> list[dict]:
    """Build YT Create → TikTok automation steps."""
    device_img = "/sdcard/DCIM/mirrorhub/product.jpg"

    steps: list[dict] = [
        # ── Push product image to phone ───────────────────────────────────────
        {"type": "push_file", "local": image_local_path, "remote": device_img,
         "label": "Upload gambar produk ke phone"},
        {"type": "wait", "seconds": 1},

        # ── Open YT Create ────────────────────────────────────────────────────
        {"type": "open_app", "package": "com.google.android.apps.youtube.creator",
         "label": "Buka YT Create"},
        {"type": "wait", "seconds": 4, "label": "Tunggu YT Create load"},

        # ── Start new project ─────────────────────────────────────────────────
        {"type": "tap_text", "text": "New project", "fallback": [0.5, 0.91],
         "label": "Tap New project"},
        {"type": "wait", "seconds": 2},

        # ── Select Script mode ────────────────────────────────────────────────
        {"type": "tap_text", "text": "Script", "fallback": [0.25, 0.45],
         "label": "Pilih Script mode"},
        {"type": "wait", "seconds": 1},

        # ── Input script ──────────────────────────────────────────────────────
        {"type": "tap_rel", "x": 0.5, "y": 0.45, "label": "Tap script input area"},
        {"type": "wait", "seconds": 0.5},
        *([{"type": "paste", "label": "Paste script dari ChatGPT"}]
          if use_clipboard else
          [{"type": "type_text", "text": script, "label": "Taip script video"}]),
        {"type": "wait", "seconds": 1},

        # ── Add product image ─────────────────────────────────────────────────
        {"type": "tap_text", "text": "Media", "fallback": [0.15, 0.85],
         "label": "Tap Media"},
        {"type": "wait", "seconds": 1},
        {"type": "tap_text", "text": "Gallery", "fallback": [0.25, 0.45],
         "label": "Pilih dari Gallery"},
        {"type": "wait", "seconds": 2},
        # Tap latest image (product yang baru dipush)
        {"type": "tap_rel", "x": 0.15, "y": 0.25, "label": "Pilih gambar produk"},
        {"type": "wait", "seconds": 0.5},
        {"type": "tap_text", "text": "Add", "fallback": [0.85, 0.92],
         "label": "Add gambar"},
        {"type": "wait", "seconds": 1},

        # ── Generate video ────────────────────────────────────────────────────
        {"type": "tap_text", "text": "Generate", "fallback": [0.5, 0.87],
         "label": "Generate video"},
        {"type": "wait", "seconds": 5, "label": "Tunggu generate mula"},
        {"type": "wait", "seconds": 90, "label": "Tunggu video siap (90 saat)"},

        # ── Continue / Next ───────────────────────────────────────────────────
        {"type": "tap_text", "text": "Continue", "fallback": [0.85, 0.12],
         "label": "Continue"},
        {"type": "wait", "seconds": 2},

        # ── Share to TikTok ───────────────────────────────────────────────────
        {"type": "tap_text", "text": "Share", "fallback": [0.85, 0.12],
         "label": "Tap Share"},
        {"type": "wait", "seconds": 2},
        {"type": "tap_text", "text": "TikTok", "fallback": [0.5, 0.55],
         "label": "Pilih TikTok"},
        {"type": "wait", "seconds": 5, "label": "Tunggu TikTok buka"},

        # ── TikTok: Next ──────────────────────────────────────────────────────
        {"type": "tap_text", "text": "Next", "fallback": [0.85, 0.07],
         "label": "Next dalam TikTok"},
        {"type": "wait", "seconds": 3},
    ]

    # ── Post type ──────────────────────────────────────────────────────────────
    if post_type == "post_now":
        steps.append({"type": "tap_text", "text": "Post", "fallback": [0.85, 0.92],
                       "label": "Post sekarang ✅"})

    elif post_type == "draft":
        steps.append({"type": "tap_text", "text": "Drafts", "fallback": [0.15, 0.92],
                       "label": "Simpan sebagai Draft ✅"})

    elif post_type == "schedule" and schedule_time:
        steps.extend([
            {"type": "tap_text", "text": "Schedule", "fallback": [0.5, 0.78],
             "label": "Tap Schedule"},
            {"type": "wait", "seconds": 1},
            {"type": "tap_text", "text": "Set time", "fallback": [0.5, 0.5],
             "label": "Set waktu"},
            {"type": "wait", "seconds": 1},
            # User needs to set time manually or via additional steps
            {"type": "tap_text", "text": "Confirm", "fallback": [0.85, 0.92],
             "label": "Confirm schedule ✅"},
        ])

    return steps
