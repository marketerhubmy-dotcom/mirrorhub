"""
Device lifecycle: hot-plug detection, DB sync, wireless auto-reconnect, event fan-out.

* Polls ``adb devices -l`` (cheap, ~30 ms) and diffs against the last snapshot.
* ``device`` state  → fetch facts, upsert the Device row (identity = hardware serial,
  so a phone moving USB ↔ WiFi stays ONE device), mark online.
* ``unauthorized`` / ``offline`` → persisted so the UI can tell the user what to do.
* A WiFi device that vanishes is re-connected with back-off unless the user asked
  to disconnect it.
* adb server death is detected, reported once, and recovered with ``start-server``.

Everything external is injectable, so the state machine is tested without adb.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device
from app.services import adb_client
from app.services.adb_client import AdbDevice, AdbError
from app.services.device_info import DeviceInfo

logger = logging.getLogger(__name__)

RECONNECT_BACKOFF_S = (2, 5, 10, 20, 40, 60)

STATE_HELP = {
    "unauthorized": "Telefon belum membenarkan PC ini. Buka telefon dan tekan 'Allow' pada dialog USB/Wireless debugging.",
    "offline": "Peranti 'offline'. Cabut dan pasang semula kabel, atau matikan dan hidupkan semula Wireless Debugging.",
    "no permissions": "Windows tiada kebenaran ke peranti. Pasang pemacu USB (OEM/Google USB driver).",
    "authorizing": "Menunggu kebenaran pada telefon…",
}


def new_device_id(adb_serial: str, hw_serial: str | None) -> str:
    """Backward compatible: legacy ids were uuid5(DNS, adb_address)."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, hw_serial or adb_serial))


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class DeviceMonitor:
    def __init__(
        self,
        *,
        session_factory: Callable[[], "AsyncSession"] | None = None,
        lister: Callable[[], Awaitable[list[AdbDevice]]] | None = None,
        info_fetcher: Callable[[str], Awaitable[DeviceInfo]] | None = None,
        connector: Callable[[str], Awaitable[tuple[bool, str]]] | None = None,
        resolver: Callable[[str, str | None], Awaitable[str | None]] | None = None,
        poll_interval: float = 2.0,
        backoff: tuple[float, ...] = RECONNECT_BACKOFF_S,
        input_prober: Callable[[str], Awaitable[tuple[str, str]]] | None = None,
        info_retries: int = 3,
        info_retry_delay: float = 1.5,
    ):
        if session_factory is None:
            from app.models.database import AsyncSessionLocal
            session_factory = AsyncSessionLocal
        if info_fetcher is None:
            from app.services.device_info import fetch_info
            info_fetcher = fetch_info
        self._sf = session_factory
        self._list = lister or adb_client.list_devices
        self._info = info_fetcher
        self._connect = connector or adb_client.connect
        self._resolve = resolver or adb_client.resolve_wifi_target
        self.poll_interval = poll_interval
        self.backoff = backoff
        self.info_retries = info_retries
        self.info_retry_delay = info_retry_delay
        self._reconciled = False

        self.known: dict[str, AdbDevice] = {}
        self.hw_of: dict[str, str] = {}              # adb serial -> hardware serial
        self.adb_ok = True
        self.last_error = ""
        self._task: asyncio.Task | None = None
        self._subs: set[asyncio.Queue] = set()
        self._reconnect: dict[str, asyncio.Task] = {}
        self._suppress: set[str] = set()             # serials the user disconnected on purpose
        self._bg: set[asyncio.Task] = set()
        self._first_tick_done = asyncio.Event()
        if input_prober is None:
            from app.services.device_ops import input_state
            input_prober = input_state
        self._probe_input = input_prober

    # ── pub/sub ───────────────────────────────────────────────────────────────

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    def _emit(self, **event) -> None:
        event.setdefault("at", datetime.now(timezone.utc).isoformat(timespec="seconds"))
        for q in list(self._subs):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                try:
                    q.get_nowait()
                    q.put_nowait(event)
                except Exception:
                    pass

    def snapshot(self) -> dict:
        return {
            "adb_ok": self.adb_ok,
            "error": self.last_error,
            "devices": [d.to_dict() | {"hw_serial": self.hw_of.get(d.serial, "")} for d in self.known.values()],
        }

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="device-monitor")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        for t in list(self._reconnect.values()) + list(self._bg):
            t.cancel()
        self._reconnect.clear()

    async def wait_first_tick(self, timeout: float = 5.0) -> bool:
        try:
            await asyncio.wait_for(self._first_tick_done.wait(), timeout)
            return True
        except asyncio.TimeoutError:
            return False

    async def _run(self) -> None:
        delay = self.poll_interval
        while True:
            try:
                await self.tick()
                delay = self.poll_interval
            except asyncio.CancelledError:
                raise
            except Exception:  # never let the monitor die
                logger.exception("device monitor tick failed")
                delay = min(delay * 2, 15)
            self._first_tick_done.set()
            await asyncio.sleep(delay)

    # ── core diff ─────────────────────────────────────────────────────────────

    async def tick(self) -> None:
        try:
            devices = await self._list()
        except adb_client.AdbMissing as exc:
            self._adb_failed(str(exc))
            return
        except AdbError as exc:
            self._adb_failed(str(exc))
            try:
                await adb_client.start_server()
            except Exception:
                pass
            return
        if not self.adb_ok:
            self.adb_ok = True
            self.last_error = ""
            self._emit(type="adb", ok=True, message="ADB pulih.")

        current = {d.serial: d for d in devices}
        if not self._reconciled:
            self._reconciled = True
            await self._reconcile_startup(current)

        for serial, dev in current.items():
            prev = self.known.get(serial)
            if prev is None:
                self._emit(type="device", action="appeared", serial=serial, state=dev.state,
                           transport=dev.transport, message=STATE_HELP.get(dev.state, ""))
                self._on_state(dev)
            elif prev.state != dev.state:
                self._emit(type="device", action="state", serial=serial, state=dev.state,
                           transport=dev.transport, previous=prev.state, message=STATE_HELP.get(dev.state, ""))
                self._on_state(dev)

        for serial, prev in list(self.known.items()):
            if serial not in current:
                self._emit(type="device", action="gone", serial=serial, state="absent", transport=prev.transport)
                self._spawn(self._on_gone(prev))

        self.known = current
        self._first_tick_done.set()

    async def _reconcile_startup(self, present: dict[str, AdbDevice]) -> None:
        """Rows left 'online' by a previous run (crash, phone unplugged while closed) must not stay online."""
        async with self._sf() as db:
            rows = (await db.execute(select(Device).where(Device.is_online.is_(True)))).scalars().all()
            changed = 0
            for row in rows:
                if row.adb_address not in present:
                    row.is_online = False
                    row.state = "offline"
                    row.last_error = "Tidak disambungkan semasa Mirrorhub dimulakan."
                    changed += 1
            if changed:
                await db.commit()
        if changed:
            logger.info("startup reconcile: %d stale online device(s) marked offline", changed)

    def _adb_failed(self, msg: str) -> None:
        if self.adb_ok or msg != self.last_error:
            self._emit(type="adb", ok=False, message=msg)
        self.adb_ok = False
        self.last_error = msg

    def _spawn(self, coro) -> None:
        t = asyncio.create_task(coro)
        self._bg.add(t)
        t.add_done_callback(self._bg.discard)

    def _on_state(self, dev: AdbDevice) -> None:
        self._suppress.discard(dev.serial)
        task = self._reconnect.pop(dev.serial, None)
        if task:
            task.cancel()
        if dev.state == "device":
            self._spawn(self._on_online(dev))
        else:
            self._spawn(self._persist_state(dev))

    # ── DB sync ───────────────────────────────────────────────────────────────

    async def _find_row(self, db: AsyncSession, serial: str, hw: str | None) -> Device | None:
        if hw:
            r = await db.execute(select(Device).where(Device.hw_serial == hw))
            row = r.scalars().first()
            if row:
                return row
        r = await db.execute(select(Device).where(Device.adb_address == serial))
        return r.scalars().first()

    async def _persist_state(self, dev: AdbDevice) -> None:
        async with self._sf() as db:
            row = await self._find_row(db, dev.serial, self.hw_of.get(dev.serial))
            if row is None:
                if dev.state in ("unauthorized", "offline", "authorizing", "no permissions"):
                    # Register a placeholder so the UI can show 'needs authorization'.
                    row = Device(
                        device_id=new_device_id(dev.serial, None),
                        device_name=dev.model or dev.serial,
                        adb_address=dev.serial,
                    )
                    db.add(row)
                else:
                    return
            row.state = "unauthorized" if dev.state == "unauthorized" else "offline"
            row.is_online = False
            row.transport = dev.transport if dev.transport in ("usb", "wifi") else row.transport
            row.last_error = STATE_HELP.get(dev.state, dev.state)
            await db.commit()
        self._emit(type="changed")

    async def _on_online(self, dev: AdbDevice) -> None:
        info: DeviceInfo | None = None
        err = ""
        for attempt in range(1, self.info_retries + 1):
            try:
                info = await self._info(dev.serial)
                err = ""
                break
            except Exception as exc:  # freshly attached devices often refuse the first shell
                err = f"Maklumat peranti tidak dapat dibaca: {exc}"
                logger.warning("info fetch %d/%d failed for %s: %s", attempt, self.info_retries, dev.serial, exc)
                if attempt < self.info_retries:
                    await asyncio.sleep(self.info_retry_delay)
        input_state = ""
        try:
            input_state, input_msg = await self._probe_input(dev.serial)
        except Exception as exc:
            logger.info("input probe failed for %s: %s", dev.serial, exc)
        hw = (info.hw_serial if info and info.hw_serial else None)
        if hw:
            self.hw_of[dev.serial] = hw
        async with self._sf() as db:
            row = await self._find_row(db, dev.serial, hw)
            if row is None:
                row = Device(
                    device_id=new_device_id(dev.serial, hw),
                    device_name=(info.model if info and info.model else dev.model or dev.serial),
                    adb_address=dev.serial,
                )
                db.add(row)
            # Prefer USB as the active route when both exist.
            current_other = row.adb_address if row.adb_address != dev.serial else None
            other = self.known.get(current_other) if current_other else None
            other_alive = other is not None and other.state == "device" and other.transport == "usb"
            if not (other_alive and dev.transport == "wifi"):
                row.adb_address = dev.serial
                row.transport = dev.transport if dev.transport in ("usb", "wifi") else "usb"
            row.state = "online"
            row.is_online = True
            row.wifi = dev.transport == "wifi"
            row.last_seen = _now()
            row.last_error = err
            row.input_state = input_state
            if hw:
                row.hw_serial = hw
            if info:
                row.model = info.model or row.model
                row.manufacturer = info.manufacturer or row.manufacturer
                row.android_version = info.android_version or row.android_version
                row.sdk = info.sdk or row.sdk
                if info.battery >= 0:
                    row.battery = info.battery
                row.storage_total_mb = info.storage_total_mb or row.storage_total_mb
                row.storage_free_mb = info.storage_free_mb or row.storage_free_mb
                row.screen_w = info.screen_w or row.screen_w
                row.screen_h = info.screen_h or row.screen_h
            await db.commit()
            device_id = row.device_id
        self._emit(type="device", action="online", serial=dev.serial, device_id=device_id,
                   state="online", transport=dev.transport)
        self._emit(type="changed")

    async def _on_gone(self, prev: AdbDevice) -> None:
        hw = self.hw_of.get(prev.serial)
        # Another route to the same phone still alive? switch to it instead of going offline.
        alt = next((s for s, h in self.hw_of.items()
                    if h == hw and s != prev.serial and s in self.known and self.known[s].state == "device"), None) if hw else None
        async with self._sf() as db:
            row = await self._find_row(db, prev.serial, hw)
            if row is None:
                return
            if alt and row.adb_address == prev.serial:
                row.adb_address = alt
                row.transport = self.known[alt].transport
            elif row.adb_address == prev.serial or alt is None:
                row.is_online = False
                row.state = "offline"
                row.last_error = "Sambungan terputus."
            await db.commit()
        self._emit(type="changed")
        if prev.transport == "wifi" and not alt and prev.serial not in self._suppress and prev.state == "device" and self._auto_reconnect_enabled():
            self._start_reconnect(prev.serial)

    # ── wireless auto-reconnect ───────────────────────────────────────────────

    @staticmethod
    def _auto_reconnect_enabled() -> bool:
        try:
            from app.services import preferences
            return bool(preferences.get("auto_reconnect"))
        except Exception:
            return True

    def _start_reconnect(self, serial: str) -> None:
        if serial in self._reconnect or not adb_client.is_wifi_reconnectable(serial):
            return
        self._reconnect[serial] = asyncio.create_task(self._reconnect_loop(serial))

    async def _reconnect_loop(self, serial: str) -> None:
        try:
            for attempt, wait in enumerate(self.backoff, 1):
                await asyncio.sleep(wait)
                if serial in self.known and self.known[serial].state == "device":
                    return
                self._emit(type="device", action="reconnecting", serial=serial, attempt=attempt,
                           of=len(self.backoff), state="reconnecting")
                await self._mark_state(serial, "reconnecting")
                try:
                    target = await self._resolve(serial, self.hw_of.get(serial))
                    if target is None:
                        ok, msg = False, "telefon tidak kelihatan melalui mDNS (Wireless debugging OFF / rangkaian berbeza)"
                    else:
                        ok, msg = await self._connect(target)
                except AdbError as exc:
                    ok, msg = False, str(exc)
                if ok:
                    # next tick sees it as appeared → _on_online
                    return
                logger.info("reconnect %s attempt %d failed: %s", serial, attempt, msg)
            await self._mark_state(serial, "offline",
                                   "Tidak dapat sambung semula. Port Wireless Debugging mungkin berubah — sambung semula dari Pairing Center.")
            self._emit(type="device", action="reconnect_failed", serial=serial, state="offline")
        finally:
            self._reconnect.pop(serial, None)

    async def _mark_state(self, serial: str, state: str, error: str = "") -> None:
        async with self._sf() as db:
            row = await self._find_row(db, serial, self.hw_of.get(serial))
            if row:
                row.state = state
                if error:
                    row.last_error = error
                await db.commit()
        self._emit(type="changed")

    # ── user intents ──────────────────────────────────────────────────────────

    def suppress_reconnect(self, serial: str) -> None:
        self._suppress.add(serial)
        t = self._reconnect.pop(serial, None)
        if t:
            t.cancel()

    async def reconnect_now(self, serial: str) -> tuple[bool, str]:
        self._suppress.discard(serial)
        target = await self._resolve(serial, self.hw_of.get(serial))
        if target is None:
            return False, "Telefon tidak kelihatan melalui mDNS. Hidupkan Wireless debugging dan pastikan rangkaian sama."
        return await self._connect(target)


def tags_to_list(raw: str | None) -> list[str]:
    try:
        v = json.loads(raw or "[]")
        return [str(x) for x in v] if isinstance(v, list) else []
    except json.JSONDecodeError:
        return []


_monitor: DeviceMonitor | None = None


def get_monitor() -> DeviceMonitor:
    global _monitor
    if _monitor is None:
        _monitor = DeviceMonitor()
    return _monitor
