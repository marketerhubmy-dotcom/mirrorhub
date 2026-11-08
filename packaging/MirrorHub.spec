# -*- mode: python ; coding: utf-8 -*-
# Build:  cd backend && .venv\Scripts\python -m PyInstaller ..\packaging\MirrorHub.spec --noconfirm --distpath ..\build\pyi-dist --workpath ..\build\pyi-work
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH).parent
BACKEND = ROOT / "backend"
DIST_UI = ROOT / "frontend" / "dist"
assert (DIST_UI / "index.html").exists(), "run `npm run build` in frontend/ first"

datas, binaries, hiddenimports = [], [], []
for pkg in ("webview", "pythonnet", "clr_loader", "proxy_tools", "bottle"):
    try:
        d, b, h = collect_all(pkg)
        datas += d; binaries += b; hiddenimports += h
    except Exception as exc:  # optional: the app falls back to the browser without them
        print("WARN collect_all failed for", pkg, exc)

hiddenimports += collect_submodules("app")
hiddenimports += collect_submodules("uvicorn")
hiddenimports += ["aiosqlite", "sqlalchemy.dialects.sqlite", "sqlalchemy.dialects.sqlite.aiosqlite",
                  "pydantic_settings", "multipart", "python_multipart", "websockets", "httpx", "bs4", "openai"]

datas += [(str(DIST_UI), "frontend/dist")]

a = Analysis(
    [str(BACKEND / "mirrorhub_app.py")],
    pathex=[str(BACKEND)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "pytest", "pytest_asyncio", "pytest_cov", "coverage", "IPython", "matplotlib", "numpy", "av"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="MirrorHub",
    console=False,
    icon=str(ROOT / "packaging" / "mirrorhub.ico"),
    version=str(ROOT / "packaging" / "version_info.txt"),
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="MirrorHub")
