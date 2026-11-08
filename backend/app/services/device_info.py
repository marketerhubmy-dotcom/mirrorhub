"""
Device facts: model, Android version, battery, storage, screen size, IP.

One ``adb shell`` round-trip gathers everything; parsing is pure and unit-tested
against realistic outputs.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict

from app.services.adb_client import AdbError, run_adb

SEP = "@@MH@@"

# Fixed script – no user input is ever interpolated into it.
_SCRIPT = ";".join([
    "getprop ro.product.model", "getprop ro.product.manufacturer", "getprop ro.build.version.release",
    "getprop ro.build.version.sdk", "getprop ro.serialno", "getprop ro.product.name",
    "dumpsys battery", "df -k /data", "wm size", "wm density", "ip -f inet addr show wlan0",
]).replace(";", f";echo {SEP};")


@dataclass
class DeviceInfo:
    model: str = ""
    manufacturer: str = ""
    android_version: str = ""
    sdk: int = 0
    hw_serial: str = ""
    product: str = ""
    battery: int = -1
    charging: bool = False
    battery_temp_c: float | None = None
    storage_total_mb: int = 0
    storage_free_mb: int = 0
    screen_w: int = 0
    screen_h: int = 0
    density: int = 0
    wifi_ip: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def parse_battery(text: str) -> tuple[int, bool, float | None]:
    level = -1
    charging = False
    temp = None
    m = re.search(r"^\s*level:\s*(\d+)", text, re.M)
    if m:
        level = int(m.group(1))
    for key in ("AC powered", "USB powered", "Wireless powered"):
        if re.search(rf"^\s*{key}:\s*true", text, re.M):
            charging = True
    m = re.search(r"^\s*status:\s*(\d+)", text, re.M)
    if m and m.group(1) == "2":  # BATTERY_STATUS_CHARGING
        charging = True
    m = re.search(r"^\s*temperature:\s*(-?\d+)", text, re.M)
    if m:
        temp = int(m.group(1)) / 10.0
    return level, charging, temp


def parse_df(text: str) -> tuple[int, int]:
    """Return (total_mb, free_mb) from `df -k /data` (toybox or busybox)."""
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[1].isdigit() and parts[3].isdigit():
            return int(parts[1]) // 1024, int(parts[3]) // 1024
    return 0, 0


def parse_wm_size(text: str) -> tuple[int, int]:
    override = re.search(r"Override size:\s*(\d+)x(\d+)", text)
    physical = re.search(r"Physical size:\s*(\d+)x(\d+)", text)
    m = override or physical
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def parse_density(text: str) -> int:
    override = re.search(r"Override density:\s*(\d+)", text)
    physical = re.search(r"Physical density:\s*(\d+)", text)
    m = override or physical
    return int(m.group(1)) if m else 0


def parse_ip(text: str) -> str:
    m = re.search(r"inet\s+(\d{1,3}(?:\.\d{1,3}){3})/", text)
    return m.group(1) if m else ""


def parse_info(output: str) -> DeviceInfo:
    sections = [s.strip() for s in output.replace("\r", "").split(SEP)]
    sections += [""] * (11 - len(sections))
    (model, manu, rel, sdk, ser, prod, batt, df, wm, dens, ip) = sections[:11]
    level, charging, temp = parse_battery(batt)
    total, free = parse_df(df)
    w, h = parse_wm_size(wm)
    return DeviceInfo(
        model=model, manufacturer=manu.title() if manu.isupper() else manu, android_version=rel,
        sdk=int(sdk) if sdk.isdigit() else 0, hw_serial=ser, product=prod,
        battery=level, charging=charging, battery_temp_c=temp,
        storage_total_mb=total, storage_free_mb=free,
        screen_w=w, screen_h=h, density=parse_density(dens), wifi_ip=parse_ip(ip),
    )


async def fetch_info(serial: str, timeout: float = 15.0) -> DeviceInfo:
    r = await run_adb("shell", _SCRIPT, serial=serial, timeout=timeout)
    if r.rc != 0 and not r.out:
        raise AdbError(r.text or "Tidak dapat membaca maklumat peranti.")
    return parse_info(r.out)
