from dataclasses import dataclass
from enum import Enum


class TikTokPhase(str, Enum):
    """High-level phases of a TikTok publish execution.

    One phase maps to one or more execution steps.
    """
    INIT           = "INIT"
    OPEN_APP       = "OPEN_APP"
    UPLOAD         = "UPLOAD"
    VIDEO_SELECTED = "VIDEO_SELECTED"
    CAPTION        = "CAPTION"
    PRODUCT        = "PRODUCT"
    VALIDATION     = "VALIDATION"
    PUBLISH        = "PUBLISH"
    VERIFY         = "VERIFY"
    DONE           = "DONE"
    FAILED         = "FAILED"


@dataclass
class PluginError:
    code: str
    reason: str
    suggested_retry: bool
    phase: TikTokPhase


ERRORS: dict[str, PluginError] = {
    "INVALID_JOB": PluginError(
        code="INVALID_JOB",
        reason="Required job fields are missing or invalid",
        suggested_retry=False,
        phase=TikTokPhase.INIT,
    ),
    "VIDEO_MISSING": PluginError(
        code="VIDEO_MISSING",
        reason="Video file not found or not readable",
        suggested_retry=False,
        phase=TikTokPhase.UPLOAD,
    ),
    "VIDEO_WRONG_FORMAT": PluginError(
        code="VIDEO_WRONG_FORMAT",
        reason="Video file format is not supported",
        suggested_retry=False,
        phase=TikTokPhase.UPLOAD,
    ),
    "UPLOAD_FAILED": PluginError(
        code="UPLOAD_FAILED",
        reason="Video failed to load in the upload preview",
        suggested_retry=True,
        phase=TikTokPhase.UPLOAD,
    ),
    "CAPTION_FAILED": PluginError(
        code="CAPTION_FAILED",
        reason="Caption could not be entered — input field not found",
        suggested_retry=True,
        phase=TikTokPhase.CAPTION,
    ),
    "PRODUCT_MISSING": PluginError(
        code="PRODUCT_MISSING",
        reason="Product not found in TikTok Shop — search returned no results",
        suggested_retry=False,
        phase=TikTokPhase.PRODUCT,
    ),
    "PRODUCT_ATTACH_FAILED": PluginError(
        code="PRODUCT_ATTACH_FAILED",
        reason="Product selector did not confirm attachment",
        suggested_retry=True,
        phase=TikTokPhase.PRODUCT,
    ),
    "NETWORK_ERROR": PluginError(
        code="NETWORK_ERROR",
        reason="Network connectivity issue detected",
        suggested_retry=True,
        phase=TikTokPhase.PUBLISH,
    ),
    "DRAFT_SAVED": PluginError(
        code="DRAFT_SAVED",
        reason="Video was saved as draft instead of published — may need manual publish",
        suggested_retry=False,
        phase=TikTokPhase.PUBLISH,
    ),
    "PUBLISH_FAILED": PluginError(
        code="PUBLISH_FAILED",
        reason="Publish action did not complete successfully",
        suggested_retry=True,
        phase=TikTokPhase.PUBLISH,
    ),
    "APP_CLOSED": PluginError(
        code="APP_CLOSED",
        reason="TikTok closed unexpectedly",
        suggested_retry=True,
        phase=TikTokPhase.OPEN_APP,
    ),
    "TIMEOUT": PluginError(
        code="TIMEOUT",
        reason="Operation timed out — device may be busy or slow",
        suggested_retry=True,
        phase=TikTokPhase.PUBLISH,
    ),
}
