"""
VisionProvider interface + concrete implementations.

Providers are pluggable: to add a new one, subclass VisionProvider,
implement analyze(), and register in _PROVIDERS.

Current providers:
  uiautomator  — ADB UI dump + rule-based classification (fast, free, offline)
  ai_vision    — GPT-4o screenshot analysis (slower, requires API key)
"""
import asyncio
import base64
import json
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from .state import ScreenAnalysis, ScreenType, ButtonTarget


class VisionProvider(ABC):
    """Interface every vision backend must implement."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def analyze(
        self,
        adb_address: str,
        device_id: str,
        image_bytes: bytes,
    ) -> ScreenAnalysis: ...


class UiAutomatorProvider(VisionProvider):
    """
    Primary provider.
    Uses ADB uiautomator dump for structured element extraction
    and rule-based screen classification — no external dependencies.
    """

    @property
    def name(self) -> str:
        return "uiautomator"

    async def analyze(
        self,
        adb_address: str,
        device_id: str,
        image_bytes: bytes,
    ) -> ScreenAnalysis:
        from .ocr import extract
        from .detector import classify_screen, detect_loading, detect_errors, detect_progress, detect_image_placeholders

        ocr = await extract(adb_address)
        screen_type, confidence = classify_screen(ocr)
        loading = detect_loading(ocr)
        errors = detect_errors(ocr)
        progress = detect_progress(ocr)
        image_placeholders = detect_image_placeholders(ocr)

        return ScreenAnalysis(
            device_id=device_id,
            screen_type=screen_type,
            screen_name=screen_type.value,
            confidence=confidence,
            visible_text=ocr.visible_text,
            buttons=ocr.buttons,
            editable_fields=ocr.editable_fields,
            dialogs=ocr.dialogs,
            loading=loading,
            errors=errors,
            progress=progress,
            image_placeholders=image_placeholders,
            raw_xml=ocr.raw_xml,
            provider=self.name,
            timestamp=datetime.now(timezone.utc),
        )


class AIVisionProvider(VisionProvider):
    """
    Optional AI provider.
    Sends screenshot to GPT-4o for semantic screen understanding.
    Falls back to UiAutomatorProvider if API key not set or call fails.

    NOTE: AI never directly executes actions — it only returns analysis.
    The Execution Engine decides whether to act on the result.
    """

    @property
    def name(self) -> str:
        return "ai_vision"

    async def analyze(
        self,
        adb_address: str,
        device_id: str,
        image_bytes: bytes,
    ) -> ScreenAnalysis:
        from app.core.config import settings
        from app.services.ai_generator import _client
        from .prompts import build_screen_analysis_prompt

        if not settings.openai_api_key or not image_bytes:
            return await UiAutomatorProvider().analyze(adb_address, device_id, image_bytes)

        b64 = base64.b64encode(image_bytes).decode()
        try:
            resp = await asyncio.to_thread(
                _client().chat.completions.create,
                model="gpt-4o",
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{b64}",
                                "detail": "low",
                            },
                        },
                        {
                            "type": "text",
                            "text": build_screen_analysis_prompt(
                                "Android automation", "any"
                            ),
                        },
                    ],
                }],
                max_tokens=500,
            )
            raw = resp.choices[0].message.content.strip()
            # Strip markdown fences if present
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            data = json.loads(raw)
        except Exception:
            return await UiAutomatorProvider().analyze(adb_address, device_id, image_bytes)

        screen_type_str = data.get("screen_type", "Unknown")
        try:
            screen_type = ScreenType(screen_type_str)
        except ValueError:
            screen_type = ScreenType.UNKNOWN

        ai_buttons = [
            ButtonTarget(
                text=b,
                x=0, y=0,
                bounds=(0, 0, 0, 0),
                confidence=0.8,
                clickable=True,
                source="ai",
            )
            for b in data.get("visible_buttons", [])
        ]

        return ScreenAnalysis(
            device_id=device_id,
            screen_type=screen_type,
            screen_name=data.get("screen_name", screen_type.value),
            confidence=float(data.get("confidence", 0.7)),
            visible_text=data.get("visible_buttons", []),
            buttons=ai_buttons,
            dialogs=data.get("dialogs", []),
            loading=bool(data.get("is_loading", False)),
            errors=data.get("errors", []),
            progress=data.get("progress_percent"),
            provider=self.name,
            ai_suggestion=data.get("suggested_action"),
            timestamp=datetime.now(timezone.utc),
        )


# Registry — extend here to add new providers
_PROVIDERS: dict[str, VisionProvider] = {
    "uiautomator": UiAutomatorProvider(),
    "ai_vision": AIVisionProvider(),
}


def get_provider(name: str = "uiautomator") -> VisionProvider:
    return _PROVIDERS.get(name, _PROVIDERS["uiautomator"])


def list_providers() -> list[str]:
    return list(_PROVIDERS.keys())
