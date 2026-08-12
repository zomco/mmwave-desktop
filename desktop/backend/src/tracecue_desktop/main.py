"""Desktop backend launcher with loopback-only binding."""

from __future__ import annotations

import os
import socket
import threading
import time
import webbrowser

import uvicorn

from .app import create_app
from .config import AppConfig
from .instance import SingleInstanceLock
from .services import DesktopServices


def _available_port(preferred: int) -> int:
    for port in range(preferred, min(preferred + 20, 65536)):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("No loopback port is available for TraceCue Desktop")


def main() -> None:
    config = AppConfig.default()
    services = DesktopServices(config)
    port = _available_port(int(services.database.settings()["preferred_port"]))
    app = create_app(config, services=services)
    if os.environ.get("TRACECUE_OPEN_BROWSER", "1") == "1":
        threading.Thread(target=_open_when_ready, args=(port,), daemon=True).start()
    with SingleInstanceLock(config.data_dir / "tracecue.lock"):
        uvicorn.run(app, host="127.0.0.1", port=port, log_config=None)


def _open_when_ready(port: int) -> None:
    for _ in range(100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.1)
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                webbrowser.open(f"http://127.0.0.1:{port}")
                return
        time.sleep(0.1)


if __name__ == "__main__":
    main()
