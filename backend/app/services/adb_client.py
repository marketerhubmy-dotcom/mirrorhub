"""
Async ADB client: device listing, wireless pairing/connect, mDNS discovery.

All argument validation lives here so API layers cannot pass shell-ish strings
to ``adb``.  Subprocesses are spawned with an argv list (never a shell), with a
timeout, and without a console window on Windows.
"""
from __future__ import annotations

import asyncio
import logging
import re
import subprocess
import sys
from dataclasses import dataclass, field

from app.utils.adb_path import ADB

logger = logging.getLogger(__name__)

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0

SERIAL_RE = re.compile(r"^[A-Za-z0-9._:\-]{1,128}$")
HOSTPORT_RE = re.compile(r"^(?:\d{1,3}(?:\.\d{1,3}){3}|[A-Za-z0-9][A-Za-z0-9.\-]{0,62}):\d{1,5}$")
PAIR_CODE_RE = re.compile(r"^\d{6}$")
IP_PORT_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}:\d{1,5}$")


class AdbError(Exception):
    """Operation failed in a way the user can act on (message is user-facing)."""


class AdbMissing(AdbError):
    """adb.exe not found at the expected location."""


@dataclass
class AdbResult:
    rc: int
    out: str
    err: str = ""

    @property
    def text(self) -> str:
        return (self.out + ("\n" + self.err if self.err else "")).strip()


@dataclass
class AdbDevice:
    serial: str
    state: str                      # device | offline | unauthorized | authorizing | no permissions | ...
    transport: str                  # usb | wifi | emulator
    model: str = ""
    product: str = ""
    device: str = ""
    transport_id: str = ""
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "serial": self.serial, "state": self.state, "transport": self.transport,
            "model": self.model, "product": self.product, "device": self.device,
            "transport_id": self.transport_id,
        }


@dataclass
class MdnsService:
    name: str
    kind: str          # pairing | connect
    address: str       # host:port

    def to_dict(self) -> dict:
        return {"name": self.name, "kind": self.kind, "address": self.address}


# ── validation ────────────────────────────────────────────────────────────────

def validate_serial(serial: str) -> str:
    if not isinstance(serial, str) or not SERIAL_RE.match(serial):
        raise AdbError("Serial peranti tidak sah.")
    return serial


def validate_hostport(addr: str) -> str:
    if not isinstance(addr, str) or not HOSTPORT_RE.match(addr.strip()):
        raise AdbError("Alamat mesti dalam format IP:PORT (contoh 192.168.1.5:37123).")
    addr = addr.strip()
    host, _, port = addr.rpartition(":")
    if not (1 <= int(port) <= 65535):
        raise AdbError("Port mesti antara 1 dan 65535.")
    if re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", host) and any(int(o) > 255 for o in host.split(".")):
        raise AdbError("Alamat IP tidak sah.")
    return addr


def validate_pair_code(code: str) -> str:
    if not isinstance(code, str) or not PAIR_CODE_RE.match(code.strip()):
        raise AdbError("Kod pairing mesti 6 digit.")
    return code.strip()


# ── runner ────────────────────────────────────────────────────────────────────

CRLF, LF = chr(13) + chr(10), chr(10)


def _build_cmd(args: tuple[str, ...], serial: str | None) -> list[str]:
    if not ADB.exists():
        raise AdbMissing(f"adb.exe tidak dijumpai di {ADB}. Pasang semula Mirrorhub.")
    cmd = [str(ADB)]
    if serial:
        cmd += ["-s", validate_serial(serial)]
    return cmd + list(args)


def _run_blocking(cmd: list[str], timeout: float, input_bytes: bytes | None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, input=input_bytes, stdin=None if input_bytes is not None else subprocess.DEVNULL,
        capture_output=True, timeout=timeout, creationflags=_NO_WINDOW,
    )


async def run_adb(*args: str, serial: str | None = None, timeout: float = 15.0,
                  input_bytes: bytes | None = None) -> AdbResult:
    """
    Run ``adb [-s serial] args...`` in a worker thread.  Raises AdbMissing / AdbError(timeout).

    Deliberately NOT asyncio.create_subprocess_exec: the device monitor calls this every 2 s, and each asyncio
    subprocess leaves pipe transports in reference cycles that only the cyclic GC frees (measured: steady idle
    memory growth).  subprocess.run in a thread has no such cycles and kills the child on timeout.
    """
    cmd = _build_cmd(args, serial)
    try:
        cp = await asyncio.to_thread(_run_blocking, cmd, timeout, input_bytes)
    except subprocess.TimeoutExpired:
        raise AdbError(f"adb tamat masa selepas {timeout:.0f}s ({' '.join(args[:3])}).") from None
    return AdbResult(
        rc=cp.returncode,
        out=cp.stdout.decode("utf-8", "replace").replace(CRLF, LF),
        err=cp.stderr.decode("utf-8", "replace").replace(CRLF, LF).strip(),
    )


async def run_adb_bytes(*args: str, serial: str | None = None, timeout: float = 30.0) -> tuple[int, bytes, str]:
    """Like run_adb but returns raw stdout bytes (screencap, exec-out)."""
    cmd = _build_cmd(args, serial)
    try:
        cp = await asyncio.to_thread(_run_blocking, cmd, timeout, None)
    except subprocess.TimeoutExpired:
        raise AdbError("adb tamat masa.") from None
    return cp.returncode or 0, cp.stdout, cp.stderr.decode("utf-8", "replace").strip()


# ── parsing ───────────────────────────────────────────────────────────────────

def classify_transport(serial: str) -> str:
    if serial.startswith("emulator-"):
        return "emulator"
    if IP_PORT_RE.match(serial) or "._adb-tls-connect." in serial or serial.startswith("adb-"):
        return "wifi"
    return "usb"


def parse_devices(output: str) -> list[AdbDevice]:
    devices: list[AdbDevice] = []
    for raw in output.splitlines():
        line = raw.strip()
        if not line or line.startswith("List of devices") or line.startswith("*"):
            continue
        parts = line.split(None, 2)
        if len(parts) < 2:
            continue
        serial, state = parts[0], parts[1]
        rest = parts[2] if len(parts) > 2 else ""
        # "no permissions (user in plugdev group; ...)" – state is the first words before key:value pairs
        if state == "no" and rest.startswith("permissions"):
            state = "no permissions"
        kv = dict(re.findall(r"(\w+):(\S+)", rest))
        devices.append(AdbDevice(
            serial=serial, state=state, transport=classify_transport(serial),
            model=kv.get("model", "").replace("_", " "), product=kv.get("product", ""),
            device=kv.get("device", ""), transport_id=kv.get("transport_id", ""),
        ))
    return devices


def parse_mdns(output: str) -> list[MdnsService]:
    out: list[MdnsService] = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 3 or not parts[1].startswith("_adb"):
            continue
        kind = "pairing" if "pairing" in parts[1] else "connect" if "connect" in parts[1] else ""
        if kind and HOSTPORT_RE.match(parts[2]):
            out.append(MdnsService(name=parts[0], kind=kind, address=parts[2]))
    return out


def interpret_pair(result: AdbResult) -> tuple[bool, str]:
    text = result.text
    low = text.lower()
    if "successfully paired" in low:
        return True, "Pairing berjaya."
    if "wrong password" in low or "failed" in low and "password" in low:
        return False, "Kod pairing salah atau sudah tamat tempoh. Tekan semula 'Pair device with pairing code' pada telefon."
    if "unable to start pairing" in low or "connection refused" in low or "cannot connect" in low:
        return False, "Tidak dapat sampai ke telefon. Pastikan alamat pairing (IP:port pada skrin pairing) betul dan satu rangkaian WiFi."
    return False, text or "Pairing gagal tanpa mesej daripada adb."


def interpret_connect(result: AdbResult) -> tuple[bool, str]:
    text = result.text
    low = text.lower()
    if "connected to" in low or "already connected" in low:
        return True, text
    if "unauthorized" in low:
        return False, "Telefon belum membenarkan komputer ini. Semak dialog 'Allow USB/Wireless debugging' pada telefon."
    if "refused" in low or "10061" in low:
        return False, "Sambungan ditolak. Port Wireless Debugging berubah setiap kali ia dihidupkan — semak port semasa pada telefon."
    if "timed out" in low or "10060" in low or "no route" in low:
        return False, "Tamat masa. Pastikan telefon dan PC dalam rangkaian WiFi yang sama dan Wireless Debugging ON."
    return False, text or "Sambungan gagal."


def is_mdns_serial(serial: str) -> bool:
    return serial.startswith("adb-") and "._adb-tls-connect." in serial


def is_wifi_reconnectable(serial: str) -> bool:
    return bool(IP_PORT_RE.match(serial)) or is_mdns_serial(serial)


async def resolve_wifi_target(serial: str, hw_serial: str | None = None) -> str | None:
    """
    Current ``ip:port`` to ``adb connect`` for a WiFi device, or None.

    * mDNS-named serial  -> look the service up by name (the port is NOT in the serial);
    * ip:port serial     -> use the mDNS entry for the same hardware serial if present (Wireless debugging rotates
                            its port on every toggle), else the old ip:port.
    """
    if not is_wifi_reconnectable(serial):
        return None
    try:
        services = [s for s in await mdns_services() if s.kind == "connect"]
    except AdbError:
        services = []
    if is_mdns_serial(serial):
        name = serial.split("._adb-tls-connect.")[0]
        for s in services:
            if s.name == name:
                return s.address
        return None
    if hw_serial:
        for s in services:
            if s.name.startswith(f"adb-{hw_serial}-"):
                return s.address
    return serial


# ── high-level operations ─────────────────────────────────────────────────────

async def start_server() -> AdbResult:
    return await run_adb("start-server", timeout=20)


async def adb_version() -> str:
    r = await run_adb("version", timeout=8)
    return r.out.splitlines()[0].strip() if r.out else r.text


async def list_devices() -> list[AdbDevice]:
    r = await run_adb("devices", "-l", timeout=10)
    if r.rc != 0:
        raise AdbError(r.text or "adb devices gagal.")
    return parse_devices(r.out)


async def pair(address: str, code: str) -> tuple[bool, str]:
    address = validate_hostport(address)
    code = validate_pair_code(code)
    # `adb pair host:port` reads the code from stdin when it is not given as an argument.
    r = await run_adb("pair", address, code, timeout=25)
    return interpret_pair(r)


async def connect(address: str) -> tuple[bool, str]:
    address = validate_hostport(address)
    r = await run_adb("connect", address, timeout=15)
    return interpret_connect(r)


async def disconnect(address: str | None = None) -> tuple[bool, str]:
    if address:
        address = validate_hostport(address)
        r = await run_adb("disconnect", address, timeout=10)
    else:
        r = await run_adb("disconnect", timeout=10)
    return r.rc == 0, r.text


async def mdns_services() -> list[MdnsService]:
    r = await run_adb("mdns", "services", timeout=8)
    if r.rc != 0:
        return []
    return parse_mdns(r.out)
