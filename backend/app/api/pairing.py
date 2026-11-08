"""
Pairing Center API — USB discovery state, ADB-over-WiFi pairing / connect / discovery.

POST /pairing/wifi/pair      {address, code}   Android 11+ "Pair device with pairing code"
POST /pairing/wifi/connect   {address}         the IP:port shown on the Wireless debugging screen
POST /pairing/wifi/disconnect{address}
GET  /pairing/wifi/discover                    mDNS: pairing + connect services seen on the LAN
GET  /pairing/status                           adb server health + live device list
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import adb_errors
from app.devices import registry
from app.devices.lifecycle import get_monitor
from app.models.database import get_db
from app.services import adb_client

router = APIRouter(prefix="/pairing", tags=["pairing"])


class PairRequest(BaseModel):
    address: str
    code: str


class AddressRequest(BaseModel):
    address: str


@router.get("/status")
async def status(db: AsyncSession = Depends(get_db)):
    mon = get_monitor()
    registered = {d.adb_address: d for d in await registry.get_all_devices(db) if d.adb_address}
    version = ""
    with adb_errors():
        version = await adb_client.adb_version()
        live = await adb_client.list_devices()
    return {
        "adb_version": version,
        "adb_ok": mon.adb_ok,
        "adb_error": mon.last_error,
        "devices": [
            d.to_dict() | {
                "registered": d.serial in registered,
                "device_id": registered[d.serial].device_id if d.serial in registered else None,
                "name": registered[d.serial].device_name if d.serial in registered else (d.model or d.serial),
            }
            for d in live
        ],
    }


@router.post("/refresh")
async def refresh():
    mon = get_monitor()
    await mon.tick()
    return mon.snapshot()


@router.get("/wifi/discover")
async def discover():
    with adb_errors():
        services = await adb_client.mdns_services()
    return {"services": [s.to_dict() for s in services]}


@router.post("/wifi/pair")
async def wifi_pair(req: PairRequest):
    with adb_errors():
        ok, msg = await adb_client.pair(req.address, req.code)
    return {"ok": ok, "message": msg}


@router.post("/wifi/connect")
async def wifi_connect(req: AddressRequest):
    with adb_errors():
        ok, msg = await adb_client.connect(req.address)
    if ok:
        await get_monitor().tick()
    return {"ok": ok, "message": msg}


@router.post("/wifi/disconnect")
async def wifi_disconnect(req: AddressRequest):
    with adb_errors():
        address = adb_client.validate_hostport(req.address)
        get_monitor().suppress_reconnect(address)
        ok, msg = await adb_client.disconnect(address)
    return {"ok": ok, "message": msg}
