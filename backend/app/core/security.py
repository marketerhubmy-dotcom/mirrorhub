"""Loopback-only hardening (docs/DECISIONS.md ADR-004, docs/AUDIT.md S2/S4).

The API controls physical phones without authentication, so it must only be
reachable by the local UI. Two browser-borne attacks are blocked here:

* cross-site WebSocket/REST requests from arbitrary web pages (Origin check);
* DNS rebinding (attacker hostname resolving to 127.0.0.1 -> Host check).
"""
from __future__ import annotations

import ipaddress
import logging
import re

logger = logging.getLogger("mirrorhub.security")

_LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]", "::1"}
_ORIGIN_RE = re.compile(r"^https?://(127\.0\.0\.1|localhost|\[::1\])(:\d{1,5})?$")
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def is_loopback_host(host: str) -> bool:
    if host in ("localhost",):
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def effective_bind_host(configured: str, allow_remote: bool = False) -> str:
    """Return the interface to bind. Non-loopback requires explicit opt-in."""
    if is_loopback_host(configured) or allow_remote:
        return configured
    logger.warning(
        "Refusing to bind control API to %r (would expose phone control to the network); "
        "using 127.0.0.1. Set ALLOW_REMOTE_BIND=true to override.", configured,
    )
    return "127.0.0.1"


def host_header_ok(host: str | None) -> bool:
    if not host:
        return False
    if host.startswith("["):  # [::1] or [::1]:8000
        name = host.split("]")[0] + "]"
    else:
        name = host.split(":")[0]
    return name in _LOCAL_HOSTS


def origin_ok(origin: str | None, extra: set[str] | frozenset[str] = frozenset()) -> bool:
    """Absent Origin = non-browser client (cannot be driven by a web page): allowed."""
    if origin is None:
        return True
    return bool(_ORIGIN_RE.match(origin)) or origin in extra


class LoopbackGuardMiddleware:
    """Pure ASGI middleware (covers both http and websocket scopes)."""

    def __init__(self, app, extra_origins: set[str] | None = None, enabled: bool = True) -> None:
        self.app = app
        self.extra = frozenset(extra_origins or ())
        self.enabled = enabled

    async def __call__(self, scope, receive, send):
        if not self.enabled or scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        is_ws = scope["type"] == "websocket"
        # Host must be a loopback name (anti DNS-rebinding). Extra origins imply their hosts.
        host_ok = host_header_ok(headers.get("host")) or (
            headers.get("host") is not None and f"http://{headers['host']}" in self.extra
        )
        check_origin = is_ws or scope.get("method", "GET") not in _SAFE_METHODS
        origin_pass = origin_ok(headers.get("origin"), self.extra) if check_origin else True

        if host_ok and origin_pass:
            return await self.app(scope, receive, send)

        logger.warning(
            "blocked %s %s host=%r origin=%r", scope["type"], scope.get("path"),
            headers.get("host"), headers.get("origin"),
        )
        if is_ws:
            await send({"type": "websocket.close", "code": 4403})
            return
        body = b'{"detail":"forbidden origin"}'
        await send({"type": "http.response.start", "status": 403,
                    "headers": [(b"content-type", b"application/json"),
                                (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})
