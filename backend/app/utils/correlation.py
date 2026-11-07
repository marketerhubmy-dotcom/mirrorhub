"""
Correlation ID — a short unique identifier that follows a request or job
through every service layer it touches.

Python contextvars propagate automatically through async coroutines spawned
in the same task tree, so the ID is available anywhere without explicit
threading.

Usage
-----
At the entry point (dispatcher tick, API request, background loop):

    from app.utils.correlation import new_correlation_id
    cid = new_correlation_id()           # generates + stores in context

Inside any called function / coroutine:

    from app.utils.correlation import get_correlation_id
    cid = get_correlation_id()           # same cid, no argument needed

To resume a known ID (e.g. from a DB job_id):

    from app.utils.correlation import set_correlation_id
    set_correlation_id(f"job-{job_id}")
"""
import uuid
from contextvars import ContextVar, Token

_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")


def new_correlation_id() -> str:
    """Generate a fresh 8-hex-char ID and bind it to the current async context."""
    cid = uuid.uuid4().hex[:8]
    _correlation_id.set(cid)
    return cid


def set_correlation_id(cid: str) -> Token:
    """
    Bind an existing ID to the current async task context.

    Returns the ContextVar Token so callers can restore the previous value
    (useful for nested scopes):

        token = set_correlation_id("job-42")
        try:
            ...
        finally:
            _correlation_id.reset(token)
    """
    return _correlation_id.set(cid)


def get_correlation_id() -> str:
    """Return the current context's correlation ID (empty string when unset)."""
    return _correlation_id.get()


def correlation_id_for(label: str, id_value: int | str) -> str:
    """
    Convenience: build and set a domain-scoped correlation ID.

    Examples:
        correlation_id_for("job", 42)       → "job-0000002a"
        correlation_id_for("goal", "abc")   → "goal-abc"
    """
    if isinstance(id_value, int):
        cid = f"{label}-{id_value:08x}"
    else:
        cid = f"{label}-{id_value}"
    _correlation_id.set(cid)
    return cid
