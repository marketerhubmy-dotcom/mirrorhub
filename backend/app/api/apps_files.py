"""
APK Manager + File Manager API.

APK library lives in <data>/apks so one upload can be installed on many phones.

GET    /apps/apks                          list library
POST   /apps/apks                          upload an .apk (multipart, streamed to disk, size-capped)
DELETE /apps/apks/{name}
GET    /apps/{id}/packages?third_party=
POST   /apps/{id}/install                  {apk, replace, grant, downgrade, allow_test}
POST   /apps/install-many                  {device_ids[], apk, ...} → per-device results
POST   /apps/{id}/uninstall|launch|force-stop|clear-data   {package, keep_data}
GET    /files/{id}/list?path=
POST   /files/{id}/mkdir|delete|rename
POST   /files/{id}/upload?dir=              multipart (many files)
GET    /files/{id}/download?path=
"""
import asyncio
import logging
import re
import shutil
import tempfile
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import adb_errors, get_online_device
from app.core import runtime_paths as rp
from app.devices import registry
from app.models.database import get_db
from app.models.device import Device
from app.services import device_ops as ops

logger = logging.getLogger(__name__)

apps_router = APIRouter(prefix="/apps", tags=["apps"])
files_router = APIRouter(prefix="/files", tags=["files"])

MAX_UPLOAD_BYTES = 4 * 1024 ** 3     # 4 GiB hard cap per file
CHUNK = 1024 * 1024
INSTALL_PARALLEL = 4


def apk_dir() -> Path:
    d = rp.data_dir() / "apks"
    d.mkdir(exist_ok=True)
    return d


def _safe_filename(raw: str | None) -> str:
    name = Path((raw or "").replace("\\", "/")).name
    name = re.sub(r"[\x00-\x1f\x7f/\\:*?\"<>|]", "_", name).strip(" .")
    return name[:200]


async def _stream_to(upload: UploadFile, dest: Path, limit: int = MAX_UPLOAD_BYTES) -> int:
    total = 0
    with dest.open("wb") as fh:
        while chunk := await upload.read(CHUNK):
            total += len(chunk)
            if total > limit:
                fh.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(413, f"Fail terlalu besar (had {limit // 1024 ** 3} GB).")
            fh.write(chunk)
    return total


# ── APK library ───────────────────────────────────────────────────────────────

@apps_router.get("/apks")
async def list_apks():
    out = []
    for f in sorted(apk_dir().glob("*.apk"), key=lambda p: p.stat().st_mtime, reverse=True):
        st = f.stat()
        out.append({"name": f.name, "size": st.st_size, "modified": st.st_mtime})
    return out


@apps_router.post("/apks")
async def upload_apk(file: UploadFile = File(...)):
    name = _safe_filename(file.filename)
    try:
        ops.validate_apk_name(name)
    except ops.OpError:
        raise HTTPException(400, "Hanya fail .apk dengan nama biasa dibenarkan.")
    dest = apk_dir() / name
    tmp = dest.with_suffix(".part")
    size = await _stream_to(file, tmp, limit=1024 ** 3)
    with tmp.open("rb") as fh:
        magic = fh.read(2)
    if magic != b"PK":                   # APKs are ZIP archives (unlink only after the handle is closed – Windows)
        tmp.unlink(missing_ok=True)
        raise HTTPException(400, "Fail ini bukan APK yang sah (bukan arkib ZIP).")
    tmp.replace(dest)
    return {"name": name, "size": size}


@apps_router.delete("/apks/{name}")
async def delete_apk(name: str):
    with adb_errors():
        ops.validate_apk_name(name)
    p = apk_dir() / name
    if not p.is_file():
        raise HTTPException(404, "APK tidak dijumpai.")
    p.unlink()
    return {"ok": True}


# ── per-device apps ───────────────────────────────────────────────────────────

class InstallRequest(BaseModel):
    apk: str
    replace: bool = True
    grant: bool = True
    downgrade: bool = False
    allow_test: bool = False


class InstallManyRequest(InstallRequest):
    device_ids: list[str]


class PackageRequest(BaseModel):
    package: str
    keep_data: bool = False


@apps_router.get("/{device_id}/packages")
async def packages(third_party: bool = Query(True), device: Device = Depends(get_online_device)):
    with adb_errors():
        pk = await ops.list_packages(device.adb_address, third_party)
    return {"packages": pk, "count": len(pk)}


@apps_router.post("/{device_id}/install")
async def install(req: InstallRequest, device: Device = Depends(get_online_device)):
    with adb_errors():
        name = ops.validate_apk_name(req.apk)
        ok, msg = await ops.install_apk(device.adb_address, apk_dir() / name, replace=req.replace,
                                        grant=req.grant, downgrade=req.downgrade, allow_test=req.allow_test)
    return {"ok": ok, "message": msg}


@apps_router.post("/install-many")
async def install_many(req: InstallManyRequest, db: AsyncSession = Depends(get_db)):
    if not req.device_ids or len(req.device_ids) > 100:
        raise HTTPException(400, "Pilih 1–100 peranti.")
    with adb_errors():
        name = ops.validate_apk_name(req.apk)
    apk = apk_dir() / name
    if not apk.is_file():
        raise HTTPException(404, "APK tidak dijumpai dalam pustaka.")
    sem = asyncio.Semaphore(INSTALL_PARALLEL)

    async def one(did: str) -> dict:
        d = await registry.get_device(db, did)
        if d is None:
            return {"device_id": did, "ok": False, "message": "Peranti tidak dijumpai."}
        if not d.is_online or not d.adb_address:
            return {"device_id": did, "name": d.device_name, "ok": False, "message": "Peranti offline."}
        async with sem:
            try:
                ok, msg = await ops.install_apk(d.adb_address, apk, replace=req.replace, grant=req.grant,
                                                downgrade=req.downgrade, allow_test=req.allow_test)
            except Exception as exc:  # one device failing must not abort the rest
                ok, msg = False, str(exc)
        return {"device_id": did, "name": d.device_name, "ok": ok, "message": msg}

    results = await asyncio.gather(*(one(i) for i in dict.fromkeys(req.device_ids)))
    return {"results": results, "succeeded": sum(r["ok"] for r in results), "total": len(results)}


@apps_router.post("/{device_id}/uninstall")
async def uninstall(req: PackageRequest, device: Device = Depends(get_online_device)):
    with adb_errors():
        ok, msg = await ops.uninstall(device.adb_address, req.package, req.keep_data)
    return {"ok": ok, "message": msg}


@apps_router.post("/{device_id}/launch")
async def launch(req: PackageRequest, device: Device = Depends(get_online_device)):
    with adb_errors():
        ok, msg = await ops.launch(device.adb_address, req.package)
    return {"ok": ok, "message": msg}


@apps_router.post("/{device_id}/force-stop")
async def force_stop(req: PackageRequest, device: Device = Depends(get_online_device)):
    with adb_errors():
        ok, msg = await ops.force_stop(device.adb_address, req.package)
    return {"ok": ok, "message": msg}


@apps_router.post("/{device_id}/clear-data")
async def clear_data(req: PackageRequest, device: Device = Depends(get_online_device)):
    with adb_errors():
        ok, msg = await ops.clear_data(device.adb_address, req.package)
    return {"ok": ok, "message": msg}


# ── files ─────────────────────────────────────────────────────────────────────

class PathRequest(BaseModel):
    path: str


class RenameRequest(PathRequest):
    new_name: str


@files_router.get("/{device_id}/list")
async def list_files(path: str = Query("/sdcard"), device: Device = Depends(get_online_device)):
    with adb_errors():
        entries = await ops.list_dir(device.adb_address, path)
        norm = ops.validate_remote_path(path)
    parent = str(PurePosixPath(norm).parent) if norm != "/" else None
    return {"path": norm, "parent": parent, "entries": [e.to_dict() for e in entries]}


@files_router.post("/{device_id}/mkdir")
async def mkdir(req: PathRequest, device: Device = Depends(get_online_device)):
    with adb_errors():
        await ops.make_dir(device.adb_address, req.path)
    return {"ok": True}


@files_router.post("/{device_id}/delete")
async def delete(req: PathRequest, device: Device = Depends(get_online_device)):
    with adb_errors():
        await ops.delete_path(device.adb_address, req.path)
    return {"ok": True}


@files_router.post("/{device_id}/rename")
async def rename(req: RenameRequest, device: Device = Depends(get_online_device)):
    with adb_errors():
        dest = await ops.rename_path(device.adb_address, req.path, req.new_name)
    return {"ok": True, "path": dest}


@files_router.post("/{device_id}/upload")
async def upload(dir: str = Query("/sdcard/Download"), files: list[UploadFile] = File(...),
                 device: Device = Depends(get_online_device)):
    if not files or len(files) > 50:
        raise HTTPException(400, "Pilih 1–50 fail.")
    results = []
    tmp_root = Path(tempfile.mkdtemp(prefix="mh-up-", dir=rp.data_dir()))
    try:
        for f in files:
            name = _safe_filename(f.filename)
            if not name:
                results.append({"name": f.filename, "ok": False, "message": "Nama fail tidak sah."})
                continue
            local = tmp_root / name
            try:
                await _stream_to(f, local)
                with adb_errors():
                    dest = await ops.push_file(device.adb_address, local, dir, name)
                results.append({"name": name, "ok": True, "path": dest})
            except HTTPException as exc:
                results.append({"name": name, "ok": False, "message": exc.detail})
            finally:
                local.unlink(missing_ok=True)
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    return {"results": results, "succeeded": sum(r["ok"] for r in results)}


@files_router.get("/{device_id}/download")
async def download(background: BackgroundTasks, path: str = Query(...), device: Device = Depends(get_online_device)):
    with adb_errors():
        remote = ops.validate_remote_path(path, allow_root=False)
        name = _safe_filename(PurePosixPath(remote).name) or "download"
        tmp_dir = Path(tempfile.mkdtemp(prefix="mh-dl-", dir=rp.data_dir()))
        try:
            local = await ops.pull_file(device.adb_address, remote, tmp_dir / name)
        except Exception:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise
    if not local.is_file():
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(400, "Hanya fail (bukan folder) boleh dimuat turun.")
    background.add_task(shutil.rmtree, tmp_dir, True)
    return FileResponse(local, filename=name, media_type="application/octet-stream")
