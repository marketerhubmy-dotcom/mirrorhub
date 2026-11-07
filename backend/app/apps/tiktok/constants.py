# TikTok Publisher plugin — configurable values.
# All timeouts are in seconds.  Change here; the plugin reads from here.

# Primary TikTok package name (most regions).  Secondary checked as fallback.
PACKAGE_NAME: str = "com.zhiliaoapp.musically"
PACKAGE_NAME_ALT: str = "com.ss.android.ugc.trill"

# ── Timeouts ──────────────────────────────────────────────────────────────────
LAUNCH_TIMEOUT: int = 15          # wait for TikTok home after monkey launch
UPLOAD_TIMEOUT: int = 30          # wait for video preview to load
CAPTION_TIMEOUT: int = 15         # wait for caption input field
PRODUCT_TIMEOUT: int = 25         # wait for product selector / search results
PUBLISH_TIMEOUT: int = 45         # wait for publish confirmation screen
VERIFY_TIMEOUT: int = 20          # wait for success indicator after publish

# ── Retry ─────────────────────────────────────────────────────────────────────
RETRY_MAX: int = 3
POLL_INTERVAL: float = 3.0        # seconds between wait_until polls

# ── Publishing behaviour ──────────────────────────────────────────────────────
PUBLISH_DELAY: float = 2.0        # pause after tapping Publish before verifying
AUTO_CONFIRM: bool = True         # auto-dismiss any confirmation dialogs
PREFERRED_UPLOAD_METHOD: str = "gallery"   # "gallery" | "files"

# ── Video validation ──────────────────────────────────────────────────────────
ALLOWED_EXTENSIONS: tuple[str, ...] = (".mp4", ".mov", ".webm")
MIN_DURATION_S: int = 3
MAX_DURATION_S: int = 600        # TikTok max 10 minutes

# ── Device paths ──────────────────────────────────────────────────────────────
DEVICE_VIDEO_DIR: str = "/sdcard/DCIM/"
DEVICE_VIDEO_FILENAME: str = "mh_tiktok.mp4"

# ── Caption ───────────────────────────────────────────────────────────────────
HASHTAG_SEPARATOR: str = " "     # character between hashtags in the final caption
HASHTAG_ORDER: str = "append"    # "append" | "prepend"
MAX_CAPTION_LENGTH: int = 2200
