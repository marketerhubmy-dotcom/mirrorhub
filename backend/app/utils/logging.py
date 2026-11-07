"""
Structured logging utility for MirrorHub.

Features
--------
* Human-readable coloured console output (default)
* Optional JSON Lines output  (LOG_FORMAT=json in .env)
* Log rotation when LOG_FILE is configured
* Correlation ID injected into every record automatically
* Secret redaction — API keys, tokens, passwords never appear in logs
* StructuredLogger.info/warning/error accept keyword arguments that
  become top-level fields in JSON output (or key=value pairs in console)

Quick start
-----------
    from app.utils.logging import get_logger
    log = get_logger(__name__)

    log.info("mirror_started", device_id="abc", pid=1234, duration_ms=50)
    log.failure("dispatch_failed", exc=exc, campaign_id=3, device_id="abc")

Never log
---------
* API keys / access tokens / passwords / full prompt text (unless
  LOG_LEVEL=DEBUG and settings.debug_prompts is True)
"""
import json
import logging
import logging.handlers
import re
import sys
from datetime import datetime, timezone
from typing import Any

# ── Secret redaction ──────────────────────────────────────────────────────────

_REDACT_KEYS: frozenset[str] = frozenset({
    "api_key", "apikey", "openai_api_key", "token", "access_token",
    "refresh_token", "password", "secret", "credential", "authorization",
    "bearer", "private_key",
})

_REDACT_RE = re.compile(
    r'("?(?:' + "|".join(re.escape(k) for k in sorted(_REDACT_KEYS)) + r')"?\s*[:=]\s*)"?[^",\s}\]]+',
    re.IGNORECASE,
)


def _redact(value: Any) -> Any:
    """Recursively redact sensitive fields from dicts / strings."""
    if isinstance(value, str):
        return _REDACT_RE.sub(r"\1[REDACTED]", value)
    if isinstance(value, dict):
        return {
            k: "[REDACTED]" if k.lower() in _REDACT_KEYS else _redact(v)
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return type(value)(_redact(item) for item in value)
    return value


# ── Formatters ────────────────────────────────────────────────────────────────

class _JSONFormatter(logging.Formatter):
    """One JSON object per log line — suitable for log aggregation pipelines."""

    def format(self, record: logging.LogRecord) -> str:
        from app.utils.correlation import get_correlation_id

        doc: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": record.name,
            "event": record.getMessage(),
        }
        cid = get_correlation_id()
        if cid:
            doc["correlation_id"] = cid

        extras: dict = getattr(record, "_structured", {})
        doc.update(_redact(extras))

        if record.exc_info:
            doc["exception"] = self.formatException(record.exc_info)

        return json.dumps(doc, default=str)


class _HumanFormatter(logging.Formatter):
    """Compact, coloured human-readable output for local development."""

    _COLORS: dict[str, str] = {
        "DEBUG":    "\033[36m",
        "INFO":     "\033[32m",
        "WARNING":  "\033[33m",
        "ERROR":    "\033[31m",
        "CRITICAL": "\033[35m",
    }
    _RESET = "\033[0m"
    _DIM   = "\033[2m"

    def format(self, record: logging.LogRecord) -> str:
        from app.utils.correlation import get_correlation_id

        ts    = datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]
        color = self._COLORS.get(record.levelname, "")
        cid   = get_correlation_id()
        cid_s = f" {self._DIM}[{cid[:8]}]{self._RESET}" if cid else ""

        extras  = getattr(record, "_structured", {})
        kv_part = " ".join(f"{k}={v!r}" for k, v in _redact(extras).items())

        msg  = record.getMessage()
        tail = f"  {kv_part}" if kv_part else ""

        exc_part = ""
        if record.exc_info:
            exc_part = "\n" + self.formatException(record.exc_info)

        return (
            f"{self._DIM}{ts}{self._RESET} "
            f"{color}{record.levelname:<8}{self._RESET} "
            f"{self._DIM}{record.name}{self._RESET}{cid_s}  "
            f"{msg}{tail}{exc_part}"
        )


# ── StructuredLogger ──────────────────────────────────────────────────────────

class StructuredLogger(logging.LoggerAdapter):
    """
    Wraps a stdlib Logger; extra keyword arguments become structured log fields.

        log.info("job_dispatched", campaign_id=3, device_id="ab12", duration_ms=42)

    In JSON mode they appear as top-level keys.
    In console mode they appear as key=value pairs after the message.
    """

    def process(self, msg: str, kwargs: dict) -> tuple[str, dict]:
        extra = dict(kwargs.pop("extra", {}))

        # Collect all "extra" kwargs (anything that's not a logging control kwarg)
        _logging_kwargs = {"exc_info", "stack_info", "stacklevel"}
        structured = {
            k: v for k, v in list(kwargs.items())
            if k not in _logging_kwargs
        }
        for k in structured:
            kwargs.pop(k)

        extra["_structured"] = structured
        kwargs["extra"] = extra
        return msg, kwargs

    def event(self, name: str, **fields: Any) -> None:
        """Alias: log.event("name", ...) → log.info("name", ...)."""
        self.info(name, **fields)

    def failure(self, name: str, exc: BaseException | None = None, **fields: Any) -> None:
        """Log at ERROR with exc_info attached."""
        self.error(name, exc_info=exc, **fields)

    def timed(self, name: str, duration_ms: float, **fields: Any) -> None:
        """Log a timed event with duration_ms attached."""
        self.info(name, duration_ms=round(duration_ms, 1), **fields)


# ── Configuration ─────────────────────────────────────────────────────────────

_configured = False


def configure_logging(
    level: str = "INFO",
    json_mode: bool = False,
    log_file: str | None = None,
) -> None:
    """
    One-time global logging configuration.

    Called from the FastAPI lifespan function. Idempotent — subsequent calls
    are no-ops so unit tests can call it without accumulating handlers.

    Parameters
    ----------
    level     : Python log level string ("DEBUG", "INFO", "WARNING", …)
    json_mode : True → emit JSON Lines; False → human-readable console
    log_file  : If set, also write JSON Lines to this rotating file
    """
    global _configured
    if _configured:
        return

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_JSONFormatter() if json_mode else _HumanFormatter())
    root.addHandler(handler)

    if log_file:
        fh = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,   # 10 MB
            backupCount=5,
            encoding="utf-8",
        )
        fh.setFormatter(_JSONFormatter())
        root.addHandler(fh)

    # Silence noisy third-party loggers
    for name in ("uvicorn.access", "sqlalchemy.engine", "httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)

    _configured = True


def get_logger(name: str) -> StructuredLogger:
    """Return a StructuredLogger wrapping the stdlib logger for *name*."""
    return StructuredLogger(logging.getLogger(name), {})


def reset_logging() -> None:
    """Remove all handlers and reset configuration (for use in tests only)."""
    global _configured
    root = logging.getLogger()
    for h in root.handlers[:]:
        root.removeHandler(h)
    _configured = False
