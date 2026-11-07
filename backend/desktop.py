"""
MirrorHub Desktop App
Launches backend + opens a native desktop window (no browser needed).
"""
import threading
import time
import sys
from pathlib import Path

import uvicorn
import webview


def _start_backend() -> None:
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        log_level="warning",
    )


def main() -> None:
    # Start backend in background thread
    thread = threading.Thread(target=_start_backend, daemon=True)
    thread.start()

    # Wait for uvicorn to be ready
    import urllib.request
    for _ in range(20):
        try:
            urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=1)
            break
        except Exception:
            time.sleep(0.5)

    # Open desktop window
    window = webview.create_window(
        title="MirrorHub",
        url="http://127.0.0.1:8000",
        width=1280,
        height=820,
        min_size=(900, 600),
        text_select=False,
    )

    webview.start(debug=False)


if __name__ == "__main__":
    main()
