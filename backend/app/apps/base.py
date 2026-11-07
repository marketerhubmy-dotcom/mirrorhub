"""
AppPlugin — interface every application plugin must implement.

Future plugins (TikTok, CapCut, Instagram) implement this same interface.
The Execution Engine never talks to plugins directly; plugins translate their
domain knowledge into step lists that the engine already understands.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class PluginResult:
    success: bool
    code: str
    reason: str
    suggested_retry: bool = False
    job_id: int | None = None
    data: dict = field(default_factory=dict)


class AppPlugin(ABC):
    """
    Required interface for every app plugin.

    Lifecycle:
        validate()  → check input before touching the device
        launch()    → open the app, wait for home screen
        prepare()   → push assets (images, audio) to device
        execute()   → build steps + hand them to ExecutionEngine
        finish()    → cleanup / post-execution verification
    """

    @property
    @abstractmethod
    def app_id(self) -> str:
        """Unique kebab-case identifier, e.g. "youtube_create"."""
        ...

    @abstractmethod
    async def validate(self, job: dict) -> PluginResult:
        """Validate job data. Returns failure before any device interaction."""
        ...

    @abstractmethod
    async def launch(self, adb_address: str, device_id: str) -> PluginResult:
        """Open the target app and confirm the home screen is visible."""
        ...

    @abstractmethod
    async def prepare(self, job: dict, adb_address: str, device_id: str) -> PluginResult:
        """Push assets and any pre-run setup that must happen outside the step flow."""
        ...

    @abstractmethod
    async def execute(self, job: dict, adb_address: str, device_id: str) -> PluginResult:
        """Build workflow steps and start execution (or simulate)."""
        ...

    @abstractmethod
    async def finish(self, job: dict, adb_address: str, device_id: str) -> PluginResult:
        """Post-execution cleanup or result verification."""
        ...
