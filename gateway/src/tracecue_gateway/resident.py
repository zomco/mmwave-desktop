"""Background entry point for the fusion review loop.

The review UI may close. This process is what keeps radar history.
Bind it to 127.0.0.1. See docs/operations/resident.md.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .fusion_store import FusionEventStore


def bind_events(store: FusionEventStore, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path.split("?", 1)[0] != "/events":
                self.send_error(404)
                return
            body = json.dumps(store.list_events()).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    return ThreadingHTTPServer((host, port), Handler)


def serve_events(store: FusionEventStore, host: str = "127.0.0.1", port: int = 8765) -> None:
    bind_events(store, host, port).serve_forever()


def load_store(path: Path) -> FusionEventStore:
    return FusionEventStore(path)


def main() -> None:
    import os

    path = Path(os.environ.get("TRACECUE_FUSION_DB", "fusion-events.sqlite"))
    host = os.environ.get("TRACECUE_FUSION_HOST", "127.0.0.1")
    port = int(os.environ.get("TRACECUE_FUSION_PORT", "8765"))
    serve_events(load_store(path), host, port)


if __name__ == "__main__":
    main()
