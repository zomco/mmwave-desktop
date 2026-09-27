"""Proxy the loopback fusion-review resident. Never opens an NVR."""

from __future__ import annotations

import json
import os
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import urlopen


def fusion_events(url: str | None = None) -> dict[str, object]:
    target = url if url is not None else os.environ.get("TRACECUE_FUSION_URL", "http://127.0.0.1:8765/events")
    parts = urlsplit(target)
    if parts.scheme != "http" or parts.hostname not in {"127.0.0.1", "localhost"} or parts.username:
        return {"available": False, "events": []}
    try:
        with urlopen(target, timeout=0.4) as response:  # noqa: S310 loopback only
            payload = json.loads(response.read(1_000_000))
    except (OSError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
        return {"available": False, "events": []}
    if not isinstance(payload, list):
        return {"available": False, "events": []}
    return {"available": True, "events": payload[:200]}
