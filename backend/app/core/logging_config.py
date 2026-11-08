"""
Centralised logging configuration for MirrorHub.

Sets up:
- Rotating file handler   → logs/mirrorhub.log (10 MB × 5 rotations)
- Console handler         → stdout, INFO+ in dev / WARNING+ in production
- Structured format       → timestamp | level | module | message

Usage:
    from app.core.logging_config import setup_logging
    setup_logging()   # called once from main.py lifespan
"""
import logging
import logging.handlers
import sys
from pathlib import Path

from app.core import runtime_paths

LOG_DIR = runtime_paths.logs_dir()
LOG_FILE = LOG_DIR / "mirrorhub.log"

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Loggers that produce too much noise at DEBUG
_NOISY_LOGGERS = [
    "uvicorn.access",
    "sqlalchemy.engine",
    "httpx",
    "httpcore",
]


def setup_logging(log_level: str = "INFO") -> None:
    """
    Configure root logger with rotating file + console handlers.

    Call once at application startup. Subsequent calls are no-ops.
    """
    root = logging.getLogger()
    if root.handlers:
        return  # already configured

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    level = getattr(logging, log_level.upper(), logging.INFO)
    root.setLevel(level)

    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

    # ── Rotating file handler ────────────────────────────────────────────────
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)
    root.addHandler(file_handler)

    # ── Console handler ──────────────────────────────────────────────────────
    # Windowed (pythonw / PyInstaller --noconsole) builds have sys.stdout is None; legacy consoles
    # are cp1252 and would raise UnicodeEncodeError on any non-Latin character in a log line.
    stream = sys.stdout
    if stream is not None:
        try:
            stream.reconfigure(errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass
        console_handler = logging.StreamHandler(stream)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(level)
        root.addHandler(console_handler)

    # Quieten noisy third-party loggers
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    logging.getLogger(__name__).info(
        "Logging initialised — level=%s file=%s", log_level, LOG_FILE
    )
