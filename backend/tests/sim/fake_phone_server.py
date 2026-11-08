"""Simulated-phone harness (NOT hardware). Runs the REAL video_endpoint/control_endpoint,
StreamHub, AnnexBSplitter and LoopbackGuard; only adb + DB are faked.
usage: python fake_phone_server.py <backend_dir> <frontend_dist> <test.h264> <port>
"""
import asyncio, sys, types
from pathlib import Path

backend, dist, h264, port = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), int(sys.argv[4])
sys.path.insert(0, str(backend))

import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.security import LoopbackGuardMiddleware
from app.services import adb_control, scrcpy_stream as ss
from app.websocket import control as control_mod, video as video_mod

DEVICES = {
    "dev-A": types.SimpleNamespace(device_id="dev-A", device_name="Fake Phone A", adb_address="10.0.0.1:5555",
                                   battery=90, wifi=True, is_online=True, state="online", last_seen="now"),
    "dev-B": types.SimpleNamespace(device_id="dev-B", device_name="Fake Phone B", adb_address="10.0.0.2:5555",
                                   battery=55, wifi=True, is_online=True, state="online", last_seen="now"),
}
import os as _os
for _i in range(int(_os.environ.get("MH_DEVICES", "2")) - 2):     # MH_DEVICES=9 -> a 9-phone wall
    DEVICES[f"dev-{_i + 3}"] = types.SimpleNamespace(device_id=f"dev-{_i + 3}", device_name=f"Fake Phone {_i + 3}",
                                                     adb_address=f"10.0.0.{_i + 3}:5555", battery=70, wifi=True, is_online=True,
                                                     state="online", last_seen="now")
LOG: list[dict] = []

# ── fake adb layer: record what would be typed into each device's shell ──
adb_control._send = lambda addr, cmd: LOG.append({"addr": addr, "cmd": cmd})
adb_control.get_screen_size = lambda addr: (1080, 2400)

async def fake_get_device(_db, device_id):
    return DEVICES.get(device_id)

video_mod.get_device = fake_get_device
control_mod.get_device = fake_get_device

# ── fake sessions feeding the REAL hub from a real H.264 file ──
data = h264.read_bytes()
splitter = ss.AnnexBSplitter()
NALS = splitter.feed(data) + splitter.flush()
asm = ss.AccessUnitAssembler()
AUS = []
for _n in NALS: AUS += asm.feed(_n)
AUS += asm.flush()

class FakeSession(ss.StreamSession):
    def start(self):
        if getattr(self, "_t", None) is None:
            self._t = asyncio.get_running_loop().create_task(self._feed())
    async def _feed(self):
        self._set("starting"); await asyncio.sleep(0.3); self._set("streaming")
        i = (hash(self.device_id) % len(AUS))
        while True:
            self.hub.push(AUS[i % len(AUS)])
            await asyncio.sleep(1 / 15)
            i += 1

class FakeManager(ss.StreamManager):
    def attach(self, device_id, serial, profile):
        key = (device_id, profile)
        s = self._sessions.get(key) or FakeSession(device_id, serial, profile)
        self._sessions[key] = s
        s.start()
        return s, s.hub.subscribe()

video_mod.stream_manager = FakeManager()

app = FastAPI()
app.add_middleware(LoopbackGuardMiddleware)

@app.get("/api/v1/devices")
async def devices(): return [vars(d) for d in DEVICES.values()]

@app.get("/api/v1/devices/{did}")
async def device(did: str): return vars(DEVICES[did])

@app.get("/api/v1/mirror/{did}/status")
async def mstatus(did: str): return {"device_id": did, "mirroring": False}

@app.get("/api/v1/system/metrics")
async def metrics():
    from app.services.metrics import process_metrics
    return {"process": process_metrics(), "streams": video_mod.stream_manager.stats()}

import os, tracemalloc
_BASE = {}
if os.environ.get("MH_TRACE"):
    tracemalloc.start(12)

@app.get("/__mem")
async def mem(reset: bool = False):
    """Leak hunting: top allocation growth since the previous reset (needs MH_TRACE=1)."""
    if not tracemalloc.is_tracing():
        return {"error": "start with MH_TRACE=1"}
    snap = tracemalloc.take_snapshot()
    if reset or "s" not in _BASE:
        _BASE["s"] = snap
        return {"reset": True}
    stats = snap.compare_to(_BASE["s"], "lineno")[:12]
    return [{"diff_kb": round(s.size_diff / 1024, 1), "count": s.count_diff, "where": str(s.traceback[0])} for s in stats]

@app.get("/__gc")
async def gc_now():
    import gc
    n = gc.collect()
    return {"collected": n}

@app.get("/__log")
async def log(): return LOG

@app.websocket("/ws/video/{device_id}")
async def wv(device_id: str, ws: WebSocket): await video_mod.video_endpoint(device_id, ws, None)

@app.websocket("/ws/control/{device_id}")
async def wc(device_id: str, ws: WebSocket): await control_mod.control_endpoint(device_id, ws, None)

app.mount("/assets", StaticFiles(directory=dist / "assets"))

@app.get("/{p:path}")
async def spa(p: str = ""): return FileResponse(dist / "index.html")

print(f"{len(NALS)} NALs / {len(AUS)} pictures loaded; serving on 127.0.0.1:{port}", flush=True)
uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning",
            ws_per_message_deflate=os.environ.get("MH_DEFLATE") == "1")
