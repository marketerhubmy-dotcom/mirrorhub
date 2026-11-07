import threading
import webbrowser
import subprocess
import sys
import time
from pathlib import Path
from PIL import Image, ImageDraw
import pystray

BASE = Path(__file__).parent.parent
BACKEND = Path(__file__).parent
FRONTEND = BASE / "frontend"


def _make_icon() -> Image.Image:
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, size - 4, size - 4], fill="#4f46e5")
    draw.text((20, 16), "M", fill="white")
    return img


def _start_backend() -> subprocess.Popen:
    venv_python = BACKEND / ".venv" / "Scripts" / "python.exe"
    return subprocess.Popen(
        [str(venv_python), "run.py"],
        cwd=str(BACKEND),
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def _start_frontend() -> subprocess.Popen:
    return subprocess.Popen(
        ["cmd", "/c", "npm run dev"],
        cwd=str(FRONTEND),
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def _open_dashboard(_icon=None, _item=None):
    webbrowser.open("http://localhost:3000")


def _open_api(_icon=None, _item=None):
    webbrowser.open("http://localhost:8000/docs")


def _quit(icon: pystray.Icon, _item, procs: list):
    for p in procs:
        try:
            p.terminate()
        except Exception:
            pass
    icon.stop()


def main():
    procs: list[subprocess.Popen] = []

    backend_proc = _start_backend()
    procs.append(backend_proc)
    time.sleep(2)

    frontend_proc = _start_frontend()
    procs.append(frontend_proc)
    time.sleep(4)

    webbrowser.open("http://localhost:3000")

    menu = pystray.Menu(
        pystray.MenuItem("Open Dashboard", _open_dashboard, default=True),
        pystray.MenuItem("API Docs", _open_api),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit MirrorHub", lambda i, it: _quit(i, it, procs)),
    )

    icon = pystray.Icon(
        "MirrorHub",
        _make_icon(),
        "MirrorHub",
        menu,
    )
    icon.run()


if __name__ == "__main__":
    main()
