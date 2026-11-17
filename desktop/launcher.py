"""Launcher desktop (pywebview + FastAPI local server) untuk distribusi standalone (.exe / .app)."""

from __future__ import annotations

import socket
import threading
import time
import urllib.request
import webbrowser

import uvicorn

from optiqm.api import create_app


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait_ready(url: str, timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{url}/api/health", timeout=1):
                return
        except Exception:
            time.sleep(0.15)


def launch() -> None:
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    app = create_app()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    _wait_ready(url)

    try:
        import webview

        webview.create_window("OptiQM Studio", url, width=1360, height=860, min_size=(960, 640))
        webview.start()
    except ImportError:
        webbrowser.open(url)
        print(f"OptiQM Studio berjalan di {url} (tekan Ctrl+C untuk keluar)")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    launch()
