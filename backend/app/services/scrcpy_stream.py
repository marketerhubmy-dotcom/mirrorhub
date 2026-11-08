"""Embedded per-device video streaming (docs/DECISIONS.md ADR-002).

Pipeline:  scrcpy-server (raw H.264, Annex-B) --adb forward--> NAL splitter
           --> StreamHub (GOP cache + per-viewer queues) --> WebSocket --> WebCodecs.

Wire format to the browser: every binary WebSocket message is ONE picture (access
unit): its NAL units, each prefixed with a 4-byte Annex-B start code. Keyframe
pictures always include SPS+PPS. Status events are JSON
text messages.

HARDWARE STATUS: the splitter/hub are unit-tested with synthetic streams. The
server-launch sequence follows the options present in the bundled scrcpy 4.0
server but has NOT been verified against a real phone (see docs/QA_MATRIX.md).
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import secrets
import subprocess
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from app.services.adb_control import validate_serial
from app.utils.adb_path import ADB, SCRCPY

logger = logging.getLogger("mirrorhub.stream")

START4 = b"\x00\x00\x00\x01"
_START3 = b"\x00\x00\x01"
NAL_IDR, NAL_SPS, NAL_PPS, NAL_SLICE = 5, 7, 8, 1
READ_SIZE = 65536
IDLE_FLUSH_S = 0.04  # > Windows timer granularity (~15.6 ms) to avoid cutting NALs mid-flight
REMOTE_JAR = "/data/local/tmp/mirrorhub-scrcpy-server.jar"
SERVER_JAR = Path(SCRCPY).parent / "scrcpy-server"

# profile -> server options (thumbnail tiles vs a focused, higher quality view)
PROFILES: dict[str, dict[str, int]] = {
    "thumb": {"max_size": 480, "max_fps": 10, "video_bit_rate": 600_000},
    "normal": {"max_size": 960, "max_fps": 24, "video_bit_rate": 3_000_000},
    "focus": {"max_size": 1280, "max_fps": 30, "video_bit_rate": 6_000_000},
}


def nal_type(nal: bytes) -> int:
    return nal[4] & 0x1F


# ── Annex-B splitter ──────────────────────────────────────────────────────────

class AnnexBSplitter:
    """Incrementally split a raw H.264 byte stream into start-code-prefixed NALs.

    A NAL is only known to be complete once the next start code arrives, so the
    trailing NAL stays pending. scrcpy emits no frames for a static screen, so
    the caller must invoke :meth:`flush` after a short idle period to release it.
    """

    MAX_BUFFER = 8 * 1024 * 1024

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> list[bytes]:
        self._buf += data
        buf = self._buf
        out: list[bytes] = []
        pos = buf.find(_START3)
        if pos < 0:
            if len(buf) > self.MAX_BUFFER:
                buf.clear()
            elif len(buf) > 3:
                del buf[:-3]  # keep a possible partial start code
            return out
        if pos > 0:
            del buf[:pos]
            pos = 0
        while True:
            nxt = buf.find(_START3, pos + 3)
            if nxt < 0:
                break
            end = nxt
            while end > pos + 3 and buf[end - 1] == 0:  # 4-byte start code / trailing zeros
                end -= 1
            if end > pos + 3:
                out.append(START4 + bytes(buf[pos + 3:end]))
            pos = nxt
        if pos:
            del buf[:pos]
        if len(buf) > self.MAX_BUFFER:  # runaway NAL, resync
            buf.clear()
        return out

    def flush(self) -> list[bytes]:
        """Emit the pending trailing NAL (assumed complete after an idle gap)."""
        buf = self._buf
        if len(buf) <= 3 or not buf.startswith(_START3):
            return []
        end = len(buf)
        while end > 3 and buf[end - 1] == 0:
            end -= 1
        nal = START4 + bytes(buf[3:end])
        buf.clear()
        return [nal] if len(nal) > 4 else []


# ── access units ──────────────────────────────────────────────────────────────

def iter_nals(au: bytes) -> list[bytes]:
    """Split a normalised access unit (4-byte start codes only) back into NALs."""
    parts = au.split(START4)
    return [START4 + p for p in parts if p]


class AccessUnitAssembler:
    """Group NALs into pictures (access units).

    Encoders may split one picture into several slices; WebCodecs needs the whole
    picture in one chunk. A new picture starts at a VCL NAL whose first_mb_in_slice
    is 0 (first payload bit set), or at SPS/PPS/SEI/AUD following VCL data. Since the
    next picture's first NAL is what completes the previous one, this adds no latency
    beyond the splitter's own (the caller flushes both after an idle gap).
    """

    def __init__(self) -> None:
        self._nals: list[bytes] = []
        self._has_vcl = False

    def _take(self) -> bytes:
        au = b"".join(self._nals)
        self._nals, self._has_vcl = [], False
        return au

    def feed(self, nal: bytes) -> list[bytes]:
        t = nal_type(nal)
        out: list[bytes] = []
        if t in (NAL_SLICE, NAL_IDR):
            first_slice = len(nal) > 5 and bool(nal[5] & 0x80)
            if self._has_vcl and first_slice:
                out.append(self._take())
            self._nals.append(nal)
            self._has_vcl = True
        elif t in (6, NAL_SPS, NAL_PPS, 9):
            if self._has_vcl:
                out.append(self._take())
            self._nals.append(nal)
        return out

    def flush(self) -> list[bytes]:
        return [self._take()] if self._has_vcl else []


# ── hub: GOP cache + per-viewer back-pressure ─────────────────────────────────

@dataclass(eq=False)  # identity semantics: viewers live in a set
class Viewer:
    queue: asyncio.Queue
    waiting_key: bool = False
    dropped: int = 0


def _unescape_rbsp(data: bytes) -> bytes:
    out = bytearray()
    zeros = 0
    for b in data:
        if zeros >= 2 and b == 3:      # emulation prevention byte
            zeros = 0
            continue
        out.append(b)
        zeros = zeros + 1 if b == 0 else 0
    return bytes(out)


class _Bits:
    def __init__(self, data: bytes) -> None:
        self.d, self.i = data, 0

    def u(self, n: int) -> int:
        v = 0
        for _ in range(n):
            byte = self.d[self.i >> 3] if (self.i >> 3) < len(self.d) else 0
            v = (v << 1) | ((byte >> (7 - (self.i & 7))) & 1)
            self.i += 1
        return v

    def ue(self) -> int:
        zeros = 0
        while self.u(1) == 0 and zeros < 32:
            zeros += 1
        return (1 << zeros) - 1 + self.u(zeros) if zeros else 0

    def se(self) -> int:
        k = self.ue()
        return (k + 1) // 2 if k & 1 else -(k // 2)


def parse_sps_size(sps_nal: bytes) -> tuple[int, int] | None:
    """Coded picture width/height (after cropping) from an H.264 SPS NAL (with start code). None if unparsable."""
    try:
        body = sps_nal[4:] if sps_nal[:4] == START4 else sps_nal[3:]
        r = _Bits(_unescape_rbsp(body[1:]))          # skip the NAL header byte
        profile = r.u(8)
        r.u(16)                                       # constraint flags + level
        r.ue()                                        # sps id
        chroma = 1
        if profile in (100, 110, 122, 244, 44, 83, 86, 118, 128, 138, 139, 134, 135):
            chroma = r.ue()
            if chroma == 3:
                r.u(1)
            r.ue(); r.ue(); r.u(1)
            if r.u(1):                                # scaling matrices
                for i in range(8 if chroma != 3 else 12):
                    if r.u(1):
                        last = nxt = 8
                        for _ in range(16 if i < 6 else 64):
                            if nxt:
                                nxt = (last + r.se() + 256) % 256
                            last = nxt or last
        r.ue()                                        # log2_max_frame_num
        poc = r.ue()
        if poc == 0:
            r.ue()
        elif poc == 1:
            r.u(1); r.se(); r.se()
            for _ in range(r.ue()):
                r.se()
        r.ue(); r.u(1)                                # max_num_ref_frames, gaps
        w_mbs, h_map = r.ue() + 1, r.ue() + 1
        frame_mbs_only = r.u(1)
        if not frame_mbs_only:
            r.u(1)
        r.u(1)
        crop = (0, 0, 0, 0)
        if r.u(1):
            crop = (r.ue(), r.ue(), r.ue(), r.ue())
        sw, sh = (2, 2) if chroma == 1 else (2, 1) if chroma == 2 else (1, 1)
        cx, cy = sw, sh * (2 - frame_mbs_only)
        w = w_mbs * 16 - cx * (crop[0] + crop[1])
        h = (2 - frame_mbs_only) * h_map * 16 - cy * (crop[2] + crop[3])
        return (w, h) if 16 <= w <= 8192 and 16 <= h <= 8192 else None
    except Exception:
        return None


class StreamHub:
    """Fan-out of access units; late joiners start from the last keyframe picture.

    Every message is one picture. Keyframe pictures are always self-contained
    (SPS+PPS prepended from cache if the encoder did not repeat them).
    """

    def __init__(self, gop_limit_bytes: int = 4 * 1024 * 1024, viewer_queue: int = 90) -> None:
        self.sps: bytes | None = None
        self.pps: bytes | None = None
        self._gop: list[bytes] = []
        self._gop_bytes = 0
        self._gop_limit = gop_limit_bytes
        self._viewer_queue = viewer_queue
        self.viewers: set[Viewer] = set()
        self.frames = 0
        self.bytes = 0
        self.width = 0
        self.height = 0
        self.first_frame_at = 0.0       # monotonic
        self.last_frame_at = 0.0
        self.dropped = 0                # pictures dropped for slow viewers (backpressure)

    def subscribe(self) -> Viewer:
        # Room for the whole cached GOP (can be hundreds of pictures) plus live headroom.
        v = Viewer(queue=asyncio.Queue(maxsize=self._viewer_queue + len(self._gop)))
        for au in self._gop:
            v.queue.put_nowait(au)
        self.viewers.add(v)
        return v

    def unsubscribe(self, v: Viewer) -> None:
        self.viewers.discard(v)

    def push(self, au: bytes) -> None:
        types = {nal_type(n) for n in iter_nals(au)}
        is_key = NAL_IDR in types
        if NAL_SPS in types or NAL_PPS in types:
            for n in iter_nals(au):
                if nal_type(n) == NAL_SPS:
                    self.sps = n
                    size = parse_sps_size(n)
                    if size:
                        self.width, self.height = size
                elif nal_type(n) == NAL_PPS:
                    self.pps = n
        if is_key and not {NAL_SPS, NAL_PPS} <= types:
            if not (self.sps and self.pps):
                return  # cannot decode a keyframe without parameter sets
            au = self.sps + self.pps + au
        if not (is_key or NAL_SLICE in types):
            return
        self.bytes += len(au)
        self.frames += 1
        now = time.monotonic()
        self.last_frame_at = now
        if not self.first_frame_at:
            self.first_frame_at = now
        if is_key:
            self._gop, self._gop_bytes = [au], len(au)
        elif self._gop:
            if self._gop_bytes + len(au) > self._gop_limit:
                self._gop, self._gop_bytes = [], 0  # too long without a keyframe: stop caching
            else:
                self._gop.append(au)
                self._gop_bytes += len(au)
        for v in list(self.viewers):
            self._deliver(v, au, is_key)

    def _deliver(self, v: Viewer, au: bytes, is_key: bool) -> None:
        if v.waiting_key:
            if not is_key:
                v.dropped += 1
                self.dropped += 1
                return
            v.waiting_key = False
        try:
            v.queue.put_nowait(au)
        except asyncio.QueueFull:
            # slow viewer: drop its backlog and wait for the next keyframe
            while not v.queue.empty():
                v.queue.get_nowait()
            v.waiting_key = not is_key
            v.dropped += 1
            self.dropped += 1
            if is_key:
                v.queue.put_nowait(au)


# ── adb helpers (monkeypatchable in tests) ────────────────────────────────────

async def run_adb(*args: str, timeout: float = 15.0) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        str(ADB), *args,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        raise
    return proc.returncode or 0, out.decode("utf-8", "replace").strip()


_server_version: str | None = None


def detect_server_version() -> str:
    """The server refuses to start unless its first argument equals its own version."""
    global _server_version
    if _server_version is None:
        override = os.environ.get("MIRRORHUB_SCRCPY_VERSION")
        if override:
            _server_version = override
        else:
            try:
                out = subprocess.run(
                    [str(SCRCPY), "--version"], capture_output=True, text=True, timeout=10,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                ).stdout
                m = re.match(r"scrcpy\s+(\S+)", out)
                _server_version = m.group(1) if m else "4.0"
            except Exception:
                _server_version = "4.0"
    return _server_version


def build_server_args(version: str, scid: str, profile: str) -> list[str]:
    p = PROFILES[profile]
    return [
        version,
        f"scid={scid}",
        "log_level=info",
        "tunnel_forward=true",
        "video=true", "audio=false", "control=false",
        "raw_stream=true",
        "send_device_meta=false", "send_frame_meta=false",
        "send_dummy_byte=false", "send_stream_meta=false",
        "video_codec=h264",
        f"max_size={p['max_size']}", f"max_fps={p['max_fps']}",
        f"video_bit_rate={p['video_bit_rate']}",
    ]


def parse_forward_port(output: str) -> int:
    m = re.search(r"\b(\d{2,5})\b", output.strip().splitlines()[-1] if output.strip() else "")
    if not m:
        raise RuntimeError(f"adb forward returned no port: {output!r}")
    return int(m.group(1))


# ── session ───────────────────────────────────────────────────────────────────

@dataclass
class StreamSession:
    device_id: str
    serial: str
    profile: str
    hub: StreamHub = field(default_factory=StreamHub)
    state: str = "idle"          # idle|starting|streaming|reconnecting|failed|stopped
    error: str = ""
    server_log: deque = field(default_factory=lambda: deque(maxlen=40))
    started_at: float = 0.0
    listeners: set = field(default_factory=set)  # callables(dict) notified on state change
    _task: asyncio.Task | None = None
    _proc: asyncio.subprocess.Process | None = None
    _port: int | None = None
    _writer: asyncio.StreamWriter | None = None
    _stop: bool = False
    # instrumentation (Performance dashboard)
    requested_at: float = 0.0        # monotonic: first start() request
    created_wall: float = field(default_factory=time.time)
    reconnects: int = 0
    last_error_msg: str = ""
    last_error_wall: float = 0.0

    MAX_RETRIES = 5

    def _set(self, state: str, error: str = "") -> None:
        prev = self.state
        self.state, self.error = state, error
        if state == "reconnecting":
            self.reconnects += 1
        if error:
            self.last_error_msg, self.last_error_wall = error, time.time()
        if state != prev or error:
            try:
                from app.services import perf_events
                perf_events.emit("stream", f"{self.profile}: {prev} -> {state}" + (f" ({error[:120]})" if error else ""),
                                 device_id=self.device_id, level="warn" if error or state in ("failed", "reconnecting") else "info",
                                 event="state", state=state, profile=self.profile)
            except Exception:
                pass
        for cb in list(self.listeners):
            try:
                cb(self.status())
            except Exception:  # a broken viewer must never break the stream
                logger.exception("stream listener failed")

    def status(self) -> dict:
        return {"event": "state", "state": self.state, "error": self.error,
                "device_id": self.device_id, "profile": self.profile}

    def startup_seconds(self) -> float | None:
        if self.requested_at and self.hub.first_frame_at:
            return round(max(0.0, self.hub.first_frame_at - self.requested_at), 2)
        return None

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop = False
        if not self.requested_at:
            self.requested_at = time.monotonic()
        self._task = asyncio.get_running_loop().create_task(self._run())

    async def stop(self) -> None:
        self._stop = True
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        await self._cleanup()
        self._set("stopped")

    async def _cleanup(self) -> None:
        if self._proc and self._proc.returncode is None:
            try:
                self._proc.kill()
            except ProcessLookupError:
                pass
        self._proc = None
        if self._writer:
            self._writer.close()
            self._writer = None
        if self._port:
            try:
                await run_adb("-s", self.serial, "forward", "--remove", f"tcp:{self._port}", timeout=5)
            except Exception:
                pass
            self._port = None

    async def _launch(self) -> asyncio.StreamReader:
        validate_serial(self.serial)
        if not SERVER_JAR.exists():
            raise RuntimeError(f"scrcpy-server not found at {SERVER_JAR}")
        code, out = await run_adb("-s", self.serial, "push", str(SERVER_JAR), REMOTE_JAR, timeout=30)
        if code != 0:
            raise RuntimeError(f"adb push failed: {out}")

        scid = f"{secrets.randbits(31):08x}"
        code, out = await run_adb("-s", self.serial, "forward", "tcp:0", f"localabstract:scrcpy_{scid}")
        if code != 0:
            raise RuntimeError(f"adb forward failed: {out}")
        self._port = parse_forward_port(out)

        args = build_server_args(detect_server_version(), scid, self.profile)
        self._proc = await asyncio.create_subprocess_exec(
            str(ADB), "-s", self.serial, "shell",
            f"CLASSPATH={REMOTE_JAR}", "app_process", "/", "com.genymobile.scrcpy.Server", *args,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        asyncio.get_running_loop().create_task(self._drain_server_log(self._proc))

        # The forward port accepts connections before the server listens; retry until bytes flow.
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if self._proc.returncode is not None:
                raise RuntimeError("scrcpy-server exited: " + " | ".join(list(self.server_log)[-5:]))
            try:
                reader, writer = await asyncio.open_connection("127.0.0.1", self._port)
            except OSError:
                await asyncio.sleep(0.25)
                continue
            try:
                first = await asyncio.wait_for(reader.read(65536), 2.0)
            except asyncio.TimeoutError:
                first = b""
            if first:
                self._first = first  # bytes already consumed while probing; _pump feeds them first
                self._writer = writer
                return reader
            writer.close()
            await asyncio.sleep(0.25)
        hint = ""
        try:
            from app.services.device_ops import screen_awake
            if await screen_awake(self.serial) is False:
                hint = "Skrin telefon mati/terkunci - hidupkan skrin telefon. "
        except Exception:
            pass
        raise RuntimeError(hint + "timed out waiting for video stream: " + " | ".join(list(self.server_log)[-5:]))

    async def _drain_server_log(self, proc: asyncio.subprocess.Process) -> None:
        try:
            while proc.stdout and (line := await proc.stdout.readline()):
                self.server_log.append(line.decode("utf-8", "replace").rstrip())
        except Exception:
            pass

    async def _pump(self, reader: asyncio.StreamReader) -> None:
        splitter, assembler = AnnexBSplitter(), AccessUnitAssembler()

        def emit(nals: list[bytes]) -> None:
            for nal in nals:
                for au in assembler.feed(nal):
                    self.hub.push(au)

        chunk = self._first
        self._first = b""
        while True:
            emit(splitter.feed(chunk))
            try:
                chunk = await asyncio.wait_for(reader.read(READ_SIZE), IDLE_FLUSH_S)
            except asyncio.TimeoutError:
                # Static screen: scrcpy sends nothing, so the last picture would sit unseen.
                # A full-size previous read means more bytes of a large NAL are likely
                # still in flight, so do not cut it short.
                if len(chunk) < READ_SIZE:
                    emit(splitter.flush())
                    for au in assembler.flush():
                        self.hub.push(au)
                chunk = await reader.read(READ_SIZE)
            if not chunk:
                emit(splitter.flush())
                for au in assembler.flush():
                    self.hub.push(au)
                raise ConnectionError("video stream closed")

    async def _run(self) -> None:
        attempt = 0
        while not self._stop:
            self._set("starting" if attempt == 0 else "reconnecting")
            try:
                reader = await self._launch()
                self.started_at = time.monotonic()
                self._set("streaming")
                attempt = 0
                await self._pump(reader)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("stream %s/%s: %s", self.device_id, self.profile, exc)
                self._set("reconnecting", str(exc))
            finally:
                await self._cleanup()
            attempt += 1
            if attempt > self.MAX_RETRIES:
                self._set("failed", self.error or "stream failed repeatedly")
                return
            await asyncio.sleep(min(0.5 * 2 ** attempt, 8))

    _first: bytes = b""


# ── manager ───────────────────────────────────────────────────────────────────

class StreamManager:
    """One session per (device_id, profile); stopped shortly after the last viewer leaves."""

    IDLE_GRACE = 5.0

    def __init__(self) -> None:
        self._sessions: dict[tuple[str, str], StreamSession] = {}
        self._reapers: dict[tuple[str, str], asyncio.Task] = {}

    def sessions(self) -> list[StreamSession]:
        return list(self._sessions.values())

    def get(self, device_id: str, profile: str) -> StreamSession | None:
        return self._sessions.get((device_id, profile))

    def attach(self, device_id: str, serial: str, profile: str) -> tuple[StreamSession, Viewer]:
        if profile not in PROFILES:
            raise ValueError(f"unknown profile {profile!r}")
        key = (device_id, profile)
        reaper = self._reapers.pop(key, None)
        if reaper:
            reaper.cancel()
        sess = self._sessions.get(key)
        if sess is None or sess.serial != serial or sess.state in ("failed", "stopped"):
            sess = StreamSession(device_id=device_id, serial=serial, profile=profile)
            self._sessions[key] = sess
        sess.start()
        return sess, sess.hub.subscribe()

    def detach(self, sess: StreamSession, viewer: Viewer) -> None:
        sess.hub.unsubscribe(viewer)
        if not sess.hub.viewers:
            key = (sess.device_id, sess.profile)
            self._reapers[key] = asyncio.get_running_loop().create_task(self._reap(key, sess))

    async def _reap(self, key: tuple[str, str], sess: StreamSession) -> None:
        try:
            await asyncio.sleep(self.IDLE_GRACE)
        except asyncio.CancelledError:
            return
        try:
            if not sess.hub.viewers:
                await sess.stop()
                if self._sessions.get(key) is sess:
                    del self._sessions[key]
        finally:
            if self._reapers.get(key) is asyncio.current_task():   # finished reapers must not accumulate
                self._reapers.pop(key, None)

    async def stop_device(self, device_id: str) -> None:
        """Stop every profile session for one device (forgotten / unplugged)."""
        for key in [k for k in self._sessions if k[0] == device_id]:
            r = self._reapers.pop(key, None)
            if r:
                r.cancel()
            await self._sessions.pop(key).stop()

    async def stop_all(self) -> None:
        for r in self._reapers.values():
            r.cancel()
        for sess in list(self._sessions.values()):
            await sess.stop()
        self._sessions.clear()

    def stats(self) -> list[dict]:
        return [
            {"device_id": s.device_id, "profile": s.profile, "state": s.state, "error": s.error,
             "viewers": len(s.hub.viewers), "frames": s.hub.frames, "bytes": s.hub.bytes,
             "uptime_s": round(time.monotonic() - s.started_at, 1) if s.started_at else 0}
            for s in self._sessions.values()
        ]


stream_manager = StreamManager()
