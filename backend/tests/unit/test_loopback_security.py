"""Origin/Host guard + bind-host policy (docs/AUDIT.md S2/S4)."""
import pytest
from fastapi import FastAPI, WebSocket
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.security import (
    LoopbackGuardMiddleware, effective_bind_host, host_header_ok, is_loopback_host, origin_ok,
)


def make_app(extra=None):
    app = FastAPI()

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    @app.post("/act")
    async def act():
        return {"acted": True}

    @app.websocket("/ws/control/{device_id}")
    async def ws(device_id: str, websocket: WebSocket):
        await websocket.accept()
        await websocket.send_json({"hello": device_id})
        await websocket.close()

    app.add_middleware(LoopbackGuardMiddleware, extra_origins=extra)
    return app


def client(host="127.0.0.1:8000", extra=None):
    return TestClient(make_app(extra), base_url=f"http://{host}")


# ── pure functions ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("h", ["127.0.0.1", "127.5.5.5", "localhost", "::1", "[::1]"])
def test_loopback_hosts(h):
    assert is_loopback_host(h)


@pytest.mark.parametrize("h", ["0.0.0.0", "192.168.1.5", "example.com", ""])
def test_non_loopback_hosts(h):
    assert not is_loopback_host(h)


def test_bind_host_refuses_all_interfaces_unless_opted_in():
    assert effective_bind_host("0.0.0.0") == "127.0.0.1"
    assert effective_bind_host("192.168.1.5") == "127.0.0.1"
    assert effective_bind_host("0.0.0.0", allow_remote=True) == "0.0.0.0"
    assert effective_bind_host("127.0.0.1") == "127.0.0.1"


@pytest.mark.parametrize("h,ok", [
    ("127.0.0.1:8000", True), ("localhost:3000", True), ("[::1]:8000", True), ("localhost", True),
    ("evil.com", False), ("evil.com:8000", False), ("127.0.0.1.evil.com", False), (None, False), ("", False),
])
def test_host_header(h, ok):
    assert host_header_ok(h) is ok


@pytest.mark.parametrize("o,ok", [
    (None, True), ("http://localhost:3000", True), ("http://127.0.0.1:8000", True),
    ("https://evil.com", False), ("http://localhost.evil.com", False), ("null", False),
    ("http://127.0.0.1:8000.evil.com", False), ("file://", False),
])
def test_origin(o, ok):
    assert origin_ok(o) is ok


# ── ASGI behaviour ────────────────────────────────────────────────────────────

# NB: websocket_connect ignores base_url for the Host header, so pass Host explicitly;
# otherwise a "blocked" result could be caused by Host and not by Origin.
LOCAL_HOST = "127.0.0.1:8000"


def test_local_ui_websocket_allowed():
    h = {"host": LOCAL_HOST, "origin": "http://127.0.0.1:8000"}
    with client().websocket_connect("/ws/control/abc", headers=h) as ws:
        assert ws.receive_json() == {"hello": "abc"}


def test_websocket_without_origin_from_local_client_allowed():
    with client().websocket_connect("/ws/control/abc", headers={"host": LOCAL_HOST}) as ws:
        assert ws.receive_json() == {"hello": "abc"}


def test_cross_site_websocket_blocked_by_origin_alone():
    h = {"host": LOCAL_HOST, "origin": "https://evil.example"}
    with pytest.raises(WebSocketDisconnect) as e:
        with client().websocket_connect("/ws/control/abc", headers=h):
            pass
    assert e.value.code == 4403


def test_dns_rebinding_host_blocked():
    h = {"host": "rebind.evil.example:8000", "origin": "http://rebind.evil.example:8000"}
    with pytest.raises(WebSocketDisconnect):
        with client().websocket_connect("/ws/control/abc", headers=h):
            pass
    assert client(host="rebind.evil.example:8000").get("/ping").status_code == 403


def test_cross_site_post_blocked_but_same_origin_post_allowed():
    c = client()
    assert c.post("/act", headers={"origin": "https://evil.example"}).status_code == 403
    assert c.post("/act", headers={"origin": "http://localhost:3000"}).status_code == 200
    assert c.post("/act").status_code == 200  # non-browser client, no Origin


def test_get_from_local_host_ok():
    assert client().get("/ping").json() == {"ok": True}


def test_configured_extra_origin_allowed():
    c = client(extra={"https://app.mirrorhub.local"})
    assert c.post("/act", headers={"origin": "https://app.mirrorhub.local"}).status_code == 200
