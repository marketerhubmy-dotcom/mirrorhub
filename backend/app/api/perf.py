"""
Performance API (read-only except thresholds and the client decoder report).

GET  /perf/overview                 cards: devices, streams, PC vs Mirrorhub CPU/RAM, FPS, reconnects, health, alerts
GET  /perf/history?range=5m|15m|1h|session
GET  /perf/devices                  per-device table (N/A + reason where not measurable)
GET  /perf/events?limit=&device_id=&kind=
GET  /perf/alerts                   active + recent history
GET  /perf/thresholds, PUT          configurable thresholds (persisted in preferences)
POST /perf/client-stats             decoder stats reported by an open Device Wall tile
GET  /perf/diagnostics              JSON report (add ?identifiers=true to keep serials/IPs; default masks them)
GET  /perf/diagnostics.txt          plain-text summary (for "copy report")
GET  /perf/export.csv?kind=history|devices|events
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.devices import registry
from app.devices.lifecycle import get_monitor, tags_to_list  # noqa: F401
from app.models.database import get_db
from app.services import perf, perf_events, perf_report, preferences

router = APIRouter(prefix="/perf", tags=["performance"])


async def _device_dicts(db: AsyncSession) -> list[dict]:
    """Registry rows from the collector's 5 s cache (no DB hit per poll); falls back to a direct read if no source is wired."""
    c = perf.get_collector()
    rows = await c.refresh_devices()
    if c._rows_at == 0.0 and not rows:                    # collector not running (tests / early startup)
        rows = []
        for d in await registry.get_all_devices(db):
            state = d.state if d.state and d.state != "absent" else ("online" if d.is_online else "offline")
            rows.append({"device_id": d.device_id, "name": d.device_name, "transport": d.transport or ("wifi" if d.wifi else "usb"),
                         "state": state, "is_online": bool(d.is_online), "battery": d.battery, "storage_free_mb": d.storage_free_mb,
                         "storage_total_mb": d.storage_total_mb, "last_error": d.last_error})
    return rows


@router.get("/snapshot")
async def snapshot(db: AsyncSession = Depends(get_db)):
    """Overview + per-device rows in ONE request (what the dashboard polls)."""
    c = perf.get_collector()
    rows = c.device_rows(await _device_dicts(db))
    return {"overview": c.overview(rows), "devices": rows}


@router.get("/overview")
async def overview(db: AsyncSession = Depends(get_db)):
    c = perf.get_collector()
    return c.overview(c.device_rows(await _device_dicts(db)))


@router.get("/history")
async def history(range: str = Query("5m", pattern="^(5m|15m|1h|session)$"), max_points: int = Query(240, ge=30, le=600)):
    c = perf.get_collector()
    return {"range": range, "interval_s": c.interval, "points": c.history(range, max_points)}


@router.get("/devices")
async def devices(db: AsyncSession = Depends(get_db)):
    c = perf.get_collector()
    return c.device_rows(await _device_dicts(db))


@router.get("/events")
async def events(limit: int = Query(100, ge=1, le=500), device_id: str | None = None, kind: str | None = None):
    return perf_events.recent(limit, device_id=device_id, kind=kind)


@router.get("/alerts")
async def alerts():
    c = perf.get_collector()
    return {"active": c.active_alerts(), "history": list(c.alert_history)[-50:]}


@router.get("/thresholds")
async def get_thresholds():
    return perf.get_collector().thresholds() | {"defaults": perf.THRESHOLD_DEFAULTS}


@router.put("/thresholds")
async def put_thresholds(patch: dict):
    bad = [k for k in patch if k not in perf.THRESHOLD_DEFAULTS]
    if bad:
        raise HTTPException(400, f"ambang tidak dikenali: {bad}")
    try:
        preferences.update(patch)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return perf.get_collector().thresholds()


class ClientStats(BaseModel):
    device_id: str = Field(max_length=64)
    profile: str = Field(max_length=16)
    received: int = Field(ge=0)
    decoded: int = Field(ge=0)
    dropped: int = Field(ge=0)
    fps: float | None = Field(None, ge=0, le=1000)
    width: int | None = Field(None, ge=0, le=16384)
    height: int | None = Field(None, ge=0, le=16384)


@router.post("/client-stats")
async def client_stats(s: ClientStats):
    perf.get_collector().report_client(s.device_id, s.profile, received=s.received, decoded=s.decoded, dropped=s.dropped,
                                       fps=s.fps, width=s.width, height=s.height)
    return {"ok": True}


async def _report(db: AsyncSession, identifiers: bool) -> dict:
    from app.services import adb_client
    from app.services.diagnostics import run_checks
    c = perf.get_collector()
    rows = c.device_rows(await _device_dicts(db))
    try:
        adb_info = {"version": await adb_client.adb_version(), "ok": get_monitor().adb_ok, "error": get_monitor().last_error}
    except Exception as exc:
        adb_info = {"version": None, "ok": False, "error": str(exc)}
    try:
        checks = await run_checks()
    except Exception:
        checks = []
    return perf_report.build_report(c, rows, adb_info, checks, include_identifiers=identifiers)


@router.get("/diagnostics")
async def diagnostics(identifiers: bool = False, db: AsyncSession = Depends(get_db)):
    return await _report(db, identifiers)


@router.get("/diagnostics.txt", response_class=PlainTextResponse)
async def diagnostics_txt(db: AsyncSession = Depends(get_db)):
    return perf_report.to_text(await _report(db, False))


@router.get("/export.csv")
async def export_csv(kind: str = Query("history", pattern="^(history|devices|events)$"), range: str = "1h",
                     db: AsyncSession = Depends(get_db)):
    c = perf.get_collector()
    if kind == "history":
        body = perf_report.history_csv(c.history(range if range in ("5m", "15m", "1h", "session") else "1h", 600))
    elif kind == "devices":
        body = perf_report.devices_csv((await _report(db, False))["devices"])
    else:
        body = perf_report.events_csv((await _report(db, False))["events"])
    return Response(body, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="mirrorhub_{kind}.csv"'})
