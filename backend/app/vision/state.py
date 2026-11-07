from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class ScreenType(str, Enum):
    HOME = "Home"
    LOADING = "Loading"
    PERMISSION_DIALOG = "Permission Dialog"
    GALLERY_PICKER = "Gallery Picker"
    SHARE_SHEET = "Share Sheet"
    EXPORT_SCREEN = "Export Screen"
    GENERATION_SCREEN = "Generation Screen"
    ERROR_DIALOG = "Error Dialog"
    CONFIRMATION_DIALOG = "Confirmation Dialog"
    UNKNOWN = "Unknown"


@dataclass
class ButtonTarget:
    text: str
    x: int
    y: int
    bounds: tuple[int, int, int, int]  # x1, y1, x2, y2
    confidence: float = 1.0
    clickable: bool = True
    source: str = "uiautomator"  # uiautomator | uiautomator_desc | ai

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "x": self.x,
            "y": self.y,
            "bounds": list(self.bounds),
            "confidence": self.confidence,
            "clickable": self.clickable,
            "source": self.source,
        }


@dataclass
class ScreenAnalysis:
    device_id: str
    screen_type: ScreenType = ScreenType.UNKNOWN
    screen_name: str = "Unknown"
    confidence: float = 0.0
    visible_text: list[str] = field(default_factory=list)
    buttons: list[ButtonTarget] = field(default_factory=list)
    dialogs: list[str] = field(default_factory=list)
    loading: bool = False
    errors: list[str] = field(default_factory=list)
    progress: float | None = None
    detected_icons: list[str] = field(default_factory=list)
    editable_fields: list[str] = field(default_factory=list)
    image_placeholders: list[str] = field(default_factory=list)
    screenshot_path: str | None = None
    width: int = 0
    height: int = 0
    raw_xml: str = ""
    provider: str = "uiautomator"
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ai_suggestion: str | None = None

    def has_button(self, *texts: str) -> bool:
        lower = {t.lower() for t in texts}
        return any(b.text.lower() in lower for b in self.buttons)

    def find_button(self, *texts: str) -> "ButtonTarget | None":
        lower = {t.lower() for t in texts}
        for b in self.buttons:
            if b.text.lower() in lower:
                return b
        # Partial match fallback
        for b in self.buttons:
            for t in lower:
                if t in b.text.lower() or b.text.lower() in t:
                    return b
        return None

    def has_text(self, *texts: str) -> bool:
        combined = " ".join(self.visible_text).lower()
        return any(t.lower() in combined for t in texts)

    def to_dict(self) -> dict:
        return {
            "device_id": self.device_id,
            "screen_type": self.screen_type.value,
            "screen_name": self.screen_name,
            "confidence": self.confidence,
            "visible_text": self.visible_text,
            "buttons": [b.to_dict() for b in self.buttons],
            "dialogs": self.dialogs,
            "loading": self.loading,
            "errors": self.errors,
            "progress": self.progress,
            "detected_icons": self.detected_icons,
            "editable_fields": self.editable_fields,
            "image_placeholders": self.image_placeholders,
            "screenshot_path": self.screenshot_path,
            "width": self.width,
            "height": self.height,
            "provider": self.provider,
            "timestamp": self.timestamp.isoformat(),
            "ai_suggestion": self.ai_suggestion,
        }
