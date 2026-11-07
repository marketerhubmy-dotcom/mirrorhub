# YouTube Create plugin — configurable values
# All timeouts are in seconds.  Change here; the plugin reads from here.

PACKAGE_NAME = "com.google.android.apps.youtube.creator"

# ── Timeouts ──────────────────────────────────────────────────────────────────
LAUNCH_TIMEOUT: int = 12          # wait for app home after monkey launch
GENERATION_TIMEOUT: int = 120     # wait for video generation to finish
EXPORT_TIMEOUT: int = 60          # wait for export to write the file
SHARE_TIMEOUT: int = 15           # wait for share sheet to open

# ── Retry ─────────────────────────────────────────────────────────────────────
RETRY_MAX: int = 3                # max retries per critical step
WAIT_POLL_INTERVAL: float = 5.0   # seconds between each wait_until poll

# ── Media ─────────────────────────────────────────────────────────────────────
PREFERRED_RESOLUTION: str = "1080p"
PREFERRED_DURATION: str = "30"    # seconds (informational — passed to YT Create)
PREFERRED_STYLE: str = "auto"
MAX_IMAGES: int = 10
DEVICE_IMAGE_DIR: str = "/sdcard/DCIM/mirrorhub"
