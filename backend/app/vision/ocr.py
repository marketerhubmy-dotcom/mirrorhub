import asyncio
import re
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from app.utils.adb_path import ADB
from .state import ButtonTarget


async def _run(adb_address: str, *args: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        str(ADB), "-s", adb_address, *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    out, _ = await proc.communicate()
    return out.decode(errors="replace")


def _parse_bounds(s: str) -> tuple[int, int, int, int]:
    m = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', s or "")
    return (int(m[1]), int(m[2]), int(m[3]), int(m[4])) if m else (0, 0, 0, 0)


@dataclass
class OcrResult:
    visible_text: list[str] = field(default_factory=list)
    buttons: list[ButtonTarget] = field(default_factory=list)
    editable_fields: list[str] = field(default_factory=list)
    dialogs: list[str] = field(default_factory=list)
    raw_xml: str = ""


def _dedup_buttons(buttons: list[ButtonTarget]) -> list[ButtonTarget]:
    """Deduplicate buttons by text, keeping first occurrence."""
    seen: set[str] = set()
    result: list[ButtonTarget] = []
    for btn in buttons:
        key = btn.text.lower()
        if key not in seen:
            seen.add(key)
            result.append(btn)
    return result


def parse_ui_xml(xml: str) -> OcrResult:
    """Parse uiautomator XML into structured OcrResult."""
    visible_text: list[str] = []
    buttons: list[ButtonTarget] = []
    editable_fields: list[str] = []
    dialogs: list[str] = []
    seen_text: set[str] = set()

    try:
        root = ET.fromstring(xml)
        nodes = list(root.iter("node"))
    except ET.ParseError:
        # Fallback: regex text extraction
        for m in re.finditer(r'text="([^"]+)"', xml):
            t = m.group(1).strip()
            if t and t not in seen_text:
                visible_text.append(t)
                seen_text.add(t)
        return OcrResult(visible_text=visible_text, raw_xml=xml)

    for node in nodes:
        text = node.get("text", "").strip()
        desc = node.get("content-desc", "").strip()
        clickable = node.get("clickable", "false") == "true"
        cls = node.get("class", "")
        bounds_str = node.get("bounds", "")

        for t in (text, desc):
            if t and t not in seen_text:
                visible_text.append(t)
                seen_text.add(t)

        if clickable and bounds_str:
            label = text or desc
            if label:
                b = _parse_bounds(bounds_str)
                cx = (b[0] + b[2]) // 2
                cy = (b[1] + b[3]) // 2
                buttons.append(ButtonTarget(
                    text=label,
                    x=cx,
                    y=cy,
                    bounds=b,
                    confidence=1.0 if text else 0.9,
                    clickable=True,
                    source="uiautomator",
                ))

        if "EditText" in cls:
            editable_fields.append(text or desc or "(empty)")

        if "Dialog" in cls and text:
            dialogs.append(text)

    return OcrResult(
        visible_text=visible_text,
        buttons=_dedup_buttons(buttons),
        editable_fields=editable_fields,
        dialogs=dialogs,
        raw_xml=xml,
    )


async def extract(adb_address: str) -> OcrResult:
    """Dump UI hierarchy via ADB and parse it."""
    await _run(adb_address, "shell", "uiautomator", "dump", "/sdcard/mh_ui.xml")
    xml = await _run(adb_address, "shell", "cat", "/sdcard/mh_ui.xml")
    return parse_ui_xml(xml)
