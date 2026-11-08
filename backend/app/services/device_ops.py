"""
Per-device operations: packages / APK, file manager, screenshot, screen recording.

Security model: nothing from the network reaches a shell unquoted.
  * package names, remote paths and file names are validated here;
  * anything interpolated into the *device* shell goes through ``sh_quote``;
  * ``adb push/pull/install`` receive argv lists (the sync protocol does not use a shell).
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from app.core import runtime_paths as rp
from app.services.adb_client import AdbError, AdbResult, run_adb, run_adb_bytes
from app.services.adb_control import sh_quote

logger = logging.getLogger(__name__)

PKG_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+$")
APK_NAME_RE = re.compile(r"^[\w .()+\-]{1,120}\.apk$", re.IGNORECASE)
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

# Never allow destructive ops on these exact paths (children are fine).
PROTECTED_PATHS = {
    "/", "/sdcard", "/storage", "/storage/emulated", "/storage/emulated/0", "/storage/self",
    "/storage/self/primary", "/data", "/data/local", "/data/data", "/system", "/vendor", "/proc",
    "/sys", "/dev", "/mnt", "/etc", "/cache", "/sdcard/Android", "/storage/emulated/0/Android",
    "/sdcard/DCIM", "/storage/emulated/0/DCIM",
}

INSTALL_ERRORS = {
    "INSTALL_FAILED_ALREADY_EXISTS": "Aplikasi sudah dipasang (cuba mod 'ganti').",
    "INSTALL_FAILED_VERSION_DOWNGRADE": "Versi APK lebih lama daripada yang dipasang. Aktifkan 'benarkan downgrade' atau nyahpasang dahulu.",
    "INSTALL_FAILED_UPDATE_INCOMPATIBLE": "Tandatangan APK tidak sepadan dengan versi sedia ada. Nyahpasang versi lama dahulu.",
    "INSTALL_FAILED_INSUFFICIENT_STORAGE": "Ruang storan telefon tidak mencukupi.",
    "INSTALL_FAILED_NO_MATCHING_ABIS": "APK tidak menyokong seni bina CPU telefon ini.",
    "INSTALL_FAILED_OLDER_SDK": "Android telefon terlalu lama untuk APK ini.",
    "INSTALL_FAILED_TEST_ONLY": "APK ditanda 'test only' (aktifkan pilihan test).",
    "INSTALL_FAILED_USER_RESTRICTED": "Telefon menyekat pemasangan melalui USB. Hidupkan 'Install via USB' dalam Developer options (Xiaomi/Oppo/Vivo) dan terima dialog pada telefon.",
    "INSTALL_PARSE_FAILED_NOT_APK": "Fail bukan APK yang sah.",
    "INSTALL_PARSE_FAILED_NO_CERTIFICATES": "APK tidak ditandatangani.",
    "INSTALL_FAILED_INVALID_APK": "APK rosak atau tidak lengkap.",
    "INSTALL_FAILED_VERIFICATION_FAILURE": "Pengesahan keselamatan telefon menolak APK (Play Protect).",
}


class OpError(AdbError):
    """Invalid request (bad name/path) – maps to HTTP 400."""


# ── validation ────────────────────────────────────────────────────────────────

def validate_package(pkg: str) -> str:
    if not isinstance(pkg, str) or len(pkg) > 255 or not PKG_RE.match(pkg):
        raise OpError("Nama pakej tidak sah (contoh: com.example.app).")
    return pkg


def validate_apk_name(name: str) -> str:
    if not isinstance(name, str) or not APK_NAME_RE.match(name) or name != Path(name).name:
        raise OpError("Nama fail APK tidak sah.")
    return name


def validate_remote_path(path: str, *, allow_root: bool = True) -> str:
    if not isinstance(path, str) or not path.startswith("/") or len(path) > 1024:
        raise OpError("Laluan peranti mesti mutlak (bermula dengan /).")
    if any(ord(c) < 32 or ord(c) == 127 for c in path):
        raise OpError("Laluan mengandungi aksara kawalan.")
    parts = path.split("/")
    if ".." in parts:
        raise OpError("Laluan tidak boleh mengandungi '..'.")
    norm = str(PurePosixPath(path))
    if not allow_root and norm == "/":
        raise OpError("Laluan akar tidak dibenarkan.")
    return norm


def validate_remote_name(name: str) -> str:
    if not isinstance(name, str) or not name or len(name) > 255 or "/" in name or name in (".", "..") \
            or any(ord(c) < 32 or ord(c) == 127 for c in name):
        raise OpError("Nama fail/folder tidak sah.")
    return name


def assert_not_protected(path: str) -> None:
    if validate_remote_path(path).rstrip("/") in PROTECTED_PATHS or path == "/":
        raise OpError(f"Laluan '{path}' dilindungi dan tidak boleh dipadam/dinamakan semula.")


# ── packages ──────────────────────────────────────────────────────────────────

def parse_packages(out: str) -> list[str]:
    return sorted({ln.strip()[len("package:"):] for ln in out.splitlines() if ln.strip().startswith("package:")})


async def list_packages(serial: str, third_party: bool = True) -> list[str]:
    args = ["shell", "pm", "list", "packages"] + (["-3"] if third_party else [])
    r = await run_adb(*args, serial=serial, timeout=20)
    if r.rc != 0:
        raise AdbError(r.text or "Gagal senaraikan aplikasi.")
    return parse_packages(r.out)


def interpret_install(result: AdbResult) -> tuple[bool, str]:
    text = result.text
    if re.search(r"^\s*Success\s*$", result.out, re.M):
        return True, "Berjaya dipasang."
    m = re.search(r"Failure\s*\[([A-Z0-9_]+)(?::[^\]]*)?\]", text)
    if m:
        code = m.group(1)
        return False, INSTALL_ERRORS.get(code, f"Pemasangan gagal: {code}")
    if "no space" in text.lower():
        return False, INSTALL_ERRORS["INSTALL_FAILED_INSUFFICIENT_STORAGE"]
    if "device offline" in text.lower() or "device not found" in text.lower():
        return False, "Peranti terputus semasa pemasangan."
    return False, text or "Pemasangan gagal tanpa mesej."


async def install_apk(serial: str, apk: Path, *, replace: bool = True, grant: bool = True,
                      downgrade: bool = False, allow_test: bool = False) -> tuple[bool, str]:
    if not apk.is_file() or apk.suffix.lower() != ".apk":
        raise OpError("Fail APK tidak dijumpai.")
    args = ["install"]
    if replace:
        args.append("-r")
    if grant:
        args.append("-g")
    if downgrade:
        args.append("-d")
    if allow_test:
        args.append("-t")
    args.append(str(apk))
    r = await run_adb(*args, serial=serial, timeout=300)
    return interpret_install(r)


async def uninstall(serial: str, pkg: str, keep_data: bool = False) -> tuple[bool, str]:
    validate_package(pkg)
    args = ["shell", "pm", "uninstall"] + (["-k"] if keep_data else []) + [pkg]
    r = await run_adb(*args, serial=serial, timeout=60)
    ok = "success" in r.out.lower()
    if ok:
        return True, "Dinyahpasang."
    if "DELETE_FAILED_INTERNAL_ERROR" in r.text:
        return False, "Gagal: aplikasi mungkin tidak dipasang, atau dilindungi (aplikasi sistem)."
    if "DELETE_FAILED_DEVICE_POLICY_MANAGER" in r.text:
        return False, "Gagal: aplikasi dilindungi oleh dasar peranti (device owner / pentadbir)."
    return False, r.text or "Nyahpasang gagal."


async def launch(serial: str, pkg: str) -> tuple[bool, str]:
    validate_package(pkg)
    r = await run_adb("shell", "monkey", "-p", pkg, "-c", "android.intent.category.LAUNCHER", "1",
                      serial=serial, timeout=20)
    ok = "events injected" in r.out.lower() and "no activities found" not in r.text.lower()
    return ok, "Dibuka." if ok else "Tidak dapat membuka aplikasi (tiada activity pelancar?)."


async def force_stop(serial: str, pkg: str) -> tuple[bool, str]:
    validate_package(pkg)
    r = await run_adb("shell", "am", "force-stop", pkg, serial=serial, timeout=15)
    return r.rc == 0, "Dihentikan." if r.rc == 0 else r.text


async def clear_data(serial: str, pkg: str) -> tuple[bool, str]:
    validate_package(pkg)
    r = await run_adb("shell", "pm", "clear", pkg, serial=serial, timeout=30)
    ok = "success" in r.out.lower()
    return ok, "Data dikosongkan." if ok else (r.text or "Gagal.")


# ── files ─────────────────────────────────────────────────────────────────────

@dataclass
class RemoteEntry:
    name: str
    is_dir: bool
    size: int
    modified: str
    perms: str
    link_to: str = ""

    def to_dict(self) -> dict:
        return self.__dict__.copy()


# toybox (Android 8+): perms links owner group size YYYY-MM-DD HH:MM name
# old toolbox (Android 5-7): perms owner group [size] YYYY-MM-DD HH:MM name   |   ... Mon dd HH:MM name
_LS = re.compile(
    r"^(?P<perm>[-dlcbps][-rwxsStT?]{9})[.+]?\s+(?:\d+\s+)?\S+\s+\S+\s+"
    r"(?:(?P<size>\d+(?:,\s*\d+)?)\s+)?"
    r"(?P<date>\d{4}-\d{2}-\d{2}|[A-Z][a-z]{2}\s+\d{1,2})\s+(?P<time>\d{2}:\d{2}|\d{4})\s+(?P<name>.+)$")


def parse_ls(out: str) -> list[RemoteEntry]:
    entries: list[RemoteEntry] = []
    for raw in out.replace("\r", "").splitlines():
        line = raw.rstrip()
        if not line or line.startswith("total "):
            continue
        m = _LS.match(line)
        if not m:
            continue
        name = m.group("name")
        link = ""
        if m.group("perm")[0] == "l" and " -> " in name:
            name, link = name.split(" -> ", 1)
        if name in (".", ".."):
            continue
        size_s = (m.group("size") or "0").split(",")[-1].strip()
        entries.append(RemoteEntry(
            name=name,
            is_dir=m.group("perm")[0] == "d" or (bool(link) and link.endswith("/")),
            size=int(size_s or 0),
            modified=f"{m.group('date')} {m.group('time')}",
            perms=m.group("perm"),
            link_to=link,
        ))
    entries.sort(key=lambda e: (not e.is_dir, e.name.lower()))
    return entries


async def list_dir(serial: str, path: str) -> list[RemoteEntry]:
    path = validate_remote_path(path)
    r = await run_adb("shell", f"ls -lA {sh_quote(path)}/", serial=serial, timeout=20)
    low = r.text.lower()
    if "no such file" in low:
        raise OpError("Folder tidak wujud.")
    if "permission denied" in low and not r.out.strip():
        raise OpError("Akses ditolak untuk folder ini.")
    if "not a directory" in low:
        raise OpError("Ini bukan folder.")
    return parse_ls(r.out)


async def make_dir(serial: str, path: str) -> None:
    path = validate_remote_path(path, allow_root=False)
    r = await run_adb("shell", f"mkdir -p {sh_quote(path)}", serial=serial, timeout=15)
    if r.rc != 0 or r.text:
        raise AdbError(r.text or "Gagal mencipta folder.")


async def delete_path(serial: str, path: str) -> None:
    path = validate_remote_path(path, allow_root=False)
    assert_not_protected(path)
    r = await run_adb("shell", f"rm -rf {sh_quote(path)}", serial=serial, timeout=60)
    if r.rc != 0 or r.text:
        raise AdbError(r.text or "Gagal memadam.")


async def rename_path(serial: str, path: str, new_name: str) -> str:
    path = validate_remote_path(path, allow_root=False)
    assert_not_protected(path)
    new_name = validate_remote_name(new_name)
    dest = str(PurePosixPath(path).parent / new_name)
    r = await run_adb("shell", f"mv {sh_quote(path)} {sh_quote(dest)}", serial=serial, timeout=30)
    if r.rc != 0 or r.text:
        raise AdbError(r.text or "Gagal menamakan semula.")
    return dest


def _transfer_ok(r: AdbResult) -> tuple[bool, str]:
    text = r.text
    if r.rc == 0 and ("pushed" in text or "pulled" in text or "file pushed" in text or "files pulled" in text):
        return True, text.splitlines()[-1] if text else "OK"
    return False, text or "Pemindahan gagal."


async def push_file(serial: str, local: Path, remote_dir: str, remote_name: str | None = None) -> str:
    remote_dir = validate_remote_path(remote_dir)
    name = validate_remote_name(remote_name or local.name)
    if not local.is_file():
        raise OpError("Fail sumber tidak dijumpai.")
    dest = str(PurePosixPath(remote_dir) / name)
    r = await run_adb("push", str(local), dest, serial=serial, timeout=1800)
    ok, msg = _transfer_ok(r)
    if not ok:
        raise AdbError(msg)
    # make new media visible to Gallery/Photos
    if PurePosixPath(dest).suffix.lower() in {".jpg", ".jpeg", ".png", ".mp4", ".mov", ".gif", ".webp", ".mp3"}:
        await run_adb("shell", "am", "broadcast", "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE",
                      "-d", f"file://{dest}", serial=serial, timeout=15)
    return dest


async def pull_file(serial: str, remote: str, local: Path) -> Path:
    remote = validate_remote_path(remote, allow_root=False)
    local.parent.mkdir(parents=True, exist_ok=True)
    r = await run_adb("pull", remote, str(local), serial=serial, timeout=1800)
    ok, msg = _transfer_ok(r)
    if not ok:
        raise AdbError(msg)
    return local


# ── input / screen state probes ───────────────────────────────────────────────

INPUT_BLOCKED_MSG = (
    "Telefon menyekat input daripada PC. Xiaomi/Redmi/Poco: hidupkan 'USB debugging (Security settings)' dalam "
    "Developer options (perlu SIM/akaun Mi). Mirrorhub tidak mengubah tetapan ini untuk anda."
)


def interpret_input_probe(result: AdbResult) -> tuple[str, str]:
    text = result.text
    if "INJECT_EVENTS" in text or "SecurityException" in text:
        return "blocked", INPUT_BLOCKED_MSG
    if result.rc == 0 and not text.strip():
        return "ok", ""
    return "unknown", text[:200]


async def input_state(serial: str) -> tuple[str, str]:
    """Send KEYCODE_UNKNOWN (a no-op key) and read the shell's answer. 'blocked' = OEM refuses injected input."""
    r = await run_adb("shell", "input", "keyevent", "KEYCODE_UNKNOWN", serial=serial, timeout=10)
    return interpret_input_probe(r)


async def screen_awake(serial: str) -> bool | None:
    r = await run_adb("shell", "dumpsys power | grep -m1 mWakefulness=", serial=serial, timeout=8)
    if "mWakefulness=" not in r.out:
        return None
    return "Awake" in r.out


# ── screenshot / recording ────────────────────────────────────────────────────

async def screenshot(serial: str) -> bytes:
    rc, out, err = await run_adb_bytes("exec-out", "screencap", "-p", serial=serial, timeout=20)
    if rc != 0 or not out.startswith(PNG_MAGIC):
        raise AdbError(err or "Skrin tidak dapat ditangkap (skrin mungkin dilindungi atau peranti terkunci).")
    return out


_recordings: dict[str, tuple[asyncio.subprocess.Process, str, float]] = {}


RECORD_TMP_DIR = "/data/local/tmp"


async def record_start(serial: str, seconds: int = 180) -> str:
    if serial in _recordings and _recordings[serial][0].returncode is None:
        raise OpError("Rakaman sedang berjalan untuk peranti ini.")
    seconds = max(5, min(int(seconds), 180))  # Android's screenrecord hard limit is 180 s
    # /data/local/tmp is shell-writable and NOT behind the /sdcard FUSE layer: on real hardware, right after a package
    # install/uninstall screenrecord blocked ~9 s in fuse_simple_request opening a /sdcard file, so an early stop
    # produced a header-only MP4.
    remote = f"{RECORD_TMP_DIR}/mirrorhub_rec_{int(time.time())}.mp4"
    from app.services.adb_client import ADB, _NO_WINDOW, validate_serial
    proc = await asyncio.create_subprocess_exec(
        str(ADB), "-s", validate_serial(serial), "shell", "screenrecord", "--time-limit", str(seconds), remote,
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL, creationflags=_NO_WINDOW,
    )
    await asyncio.sleep(0.8)
    if proc.returncode not in (None, 0):
        raise AdbError("screenrecord tidak dapat dimulakan pada peranti ini.")
    _recordings[serial] = (proc, remote, time.time())
    return remote


async def record_stop(serial: str) -> Path:
    entry = _recordings.pop(serial, None)
    if not entry:
        raise OpError("Tiada rakaman aktif.")
    proc, remote, _ = entry
    if proc.returncode is None:
        # SIGINT lets screenrecord finalise the MP4 container.
        await run_adb("shell", "pkill -2 screenrecord || killall -2 screenrecord", serial=serial, timeout=10)
        try:
            await asyncio.wait_for(proc.wait(), 8)
        except asyncio.TimeoutError:
            proc.kill()
    # Wait until the file stops growing: screenrecord writes the MP4 index (moov) only when it finalises.
    last = -1
    for _ in range(20):
        r = await run_adb("shell", f"stat -c %s {sh_quote(remote)}", serial=serial, timeout=10)
        size = int(r.out.strip()) if r.out.strip().isdigit() else 0
        if size == last and size > 0:
            break
        last = size
        await asyncio.sleep(0.4)
    out_dir = rp.data_dir() / "recordings"
    out_dir.mkdir(exist_ok=True)
    local = out_dir / f"{re.sub(r'[^A-Za-z0-9._-]', '_', serial)}_{int(time.time() * 1000)}.mp4"
    await pull_file(serial, remote, local)
    if not mp4_is_complete(local):
        # observed intermittently on real hardware (header-only file): never hand the user a broken video silently
        local.unlink(missing_ok=True)
        await run_adb("shell", f"rm -f {sh_quote(remote)}", serial=serial, timeout=10)
        raise AdbError("Rakaman tidak lengkap (screenrecord tidak sempat menulis fail). Cuba lagi; elakkan menghentikan "
                       "rakaman terlalu awal atau semasa pengekod video sedang sibuk.")
    await run_adb("shell", f"rm -f {sh_quote(remote)}", serial=serial, timeout=10)
    return local


def mp4_is_complete(path: Path) -> bool:
    """A finished screenrecord MP4 has an 'ftyp' header and a 'moov' index (written last)."""
    try:
        size = path.stat().st_size
        if size < 4096:
            return False
        with path.open("rb") as f:
            head = f.read(64)
            f.seek(max(0, size - 4 * 1024 * 1024))
            tail = f.read()
        return head[4:8] == b"ftyp" and b"moov" in (tail if size > 4 * 1024 * 1024 else head + tail)
    except OSError:
        return False


def recording_active(serial: str) -> bool:
    e = _recordings.get(serial)
    return bool(e and e[0].returncode is None)
