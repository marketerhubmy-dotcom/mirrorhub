from dataclasses import dataclass
from enum import Enum

from .constants import MAX_IMAGES


class YouTubeCreatePhase(str, Enum):
    """High-level phases of a YouTube Create execution.

    This is the plugin-level state machine — coarser than the per-step states
    tracked by the Execution Engine.  One phase maps to one or more steps.
    """
    INIT           = "INIT"
    OPEN_APP       = "OPEN_APP"
    CREATE_PROJECT = "CREATE_PROJECT"
    INPUT_PROMPT   = "INPUT_PROMPT"
    IMPORT_IMAGES  = "IMPORT_IMAGES"
    GENERATE       = "GENERATE"
    WAIT_GENERATION = "WAIT_GENERATION"
    EXPORT         = "EXPORT"
    SHARE          = "SHARE"
    DONE           = "DONE"
    FAILED         = "FAILED"


@dataclass
class PluginError:
    code: str
    reason: str
    suggested_retry: bool
    phase: YouTubeCreatePhase


# Catalogue of every named error condition the plugin can surface
ERRORS: dict[str, PluginError] = {
    "GENERATION_FAILED": PluginError(
        code="GENERATION_FAILED",
        reason="Video generation did not complete within the configured timeout",
        suggested_retry=True,
        phase=YouTubeCreatePhase.WAIT_GENERATION,
    ),
    "PROMPT_REJECTED": PluginError(
        code="PROMPT_REJECTED",
        reason="Prompt was rejected or flagged by YouTube Create",
        suggested_retry=False,
        phase=YouTubeCreatePhase.INPUT_PROMPT,
    ),
    "NETWORK_ERROR": PluginError(
        code="NETWORK_ERROR",
        reason="Network connectivity issue detected during generation",
        suggested_retry=True,
        phase=YouTubeCreatePhase.GENERATE,
    ),
    "APP_CLOSED": PluginError(
        code="APP_CLOSED",
        reason="YouTube Create closed unexpectedly",
        suggested_retry=True,
        phase=YouTubeCreatePhase.OPEN_APP,
    ),
    "TIMEOUT": PluginError(
        code="TIMEOUT",
        reason="Operation timed out — device may be busy or slow",
        suggested_retry=True,
        phase=YouTubeCreatePhase.WAIT_GENERATION,
    ),
    "EXPORT_FAILED": PluginError(
        code="EXPORT_FAILED",
        reason="Video export step did not complete",
        suggested_retry=True,
        phase=YouTubeCreatePhase.EXPORT,
    ),
    "SHARE_FAILED": PluginError(
        code="SHARE_FAILED",
        reason="Share sheet did not open or target app not found",
        suggested_retry=True,
        phase=YouTubeCreatePhase.SHARE,
    ),
    "INVALID_JOB": PluginError(
        code="INVALID_JOB",
        reason="Required job fields are missing or invalid",
        suggested_retry=False,
        phase=YouTubeCreatePhase.INIT,
    ),
    "MISSING_IMAGE": PluginError(
        code="MISSING_IMAGE",
        reason="One or more reference image files were not found on disk",
        suggested_retry=False,
        phase=YouTubeCreatePhase.IMPORT_IMAGES,
    ),
    "TOO_MANY_IMAGES": PluginError(
        code="TOO_MANY_IMAGES",
        reason=f"Maximum {MAX_IMAGES} reference images allowed",
        suggested_retry=False,
        phase=YouTubeCreatePhase.IMPORT_IMAGES,
    ),
}
