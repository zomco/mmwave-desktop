"""Bounded acquisition adapters and deterministic fixture replay."""

from __future__ import annotations

import json
import socket
from collections import deque
from datetime import datetime, timezone
from typing import Iterable, Protocol

from tracecue_engine import parse_rfc3339

from .models import Observation


MAX_LINE_BYTES = 16 * 1024


class AcquisitionAdapter(Protocol):
    adapter_name: str
    model_identity: str

    def read(self) -> Observation: ...
    def reconnect(self) -> None: ...
    def close(self) -> None: ...


class JsonLineTcpAdapter:
    """Experimental HA-free adapter for a documented JSON-line bridge.

    This is a transport surface, not a commercial hardware certification.
    """

    adapter_name = "json-line-tcp.experimental"

    def __init__(
        self,
        host: str,
        port: int,
        *,
        source_id: str,
        channel_id: str,
        model_identity: str,
        timeout_seconds: float = 5.0,
    ):
        self.host = host
        self.port = port
        self.source_id = source_id
        self.channel_id = channel_id
        self.model_identity = model_identity
        self.timeout_seconds = timeout_seconds
        self._socket: socket.socket | None = None
        self._file = None

    def reconnect(self) -> None:
        self.close()
        connection = socket.create_connection((self.host, self.port), timeout=self.timeout_seconds)
        connection.settimeout(self.timeout_seconds)
        self._socket = connection
        self._file = connection.makefile("rb")

    def read(self) -> Observation:
        if self._file is None:
            self.reconnect()
        line = self._file.readline(MAX_LINE_BYTES + 1)
        if not line:
            raise ConnectionError("sensor bridge closed the connection")
        if len(line) > MAX_LINE_BYTES or not line.endswith(b"\n"):
            raise ValueError("sensor observation exceeds the line-size limit")
        try:
            payload = json.loads(line)
            source_at = parse_rfc3339(payload["timestamp"], "timestamp")
            track_id = str(payload["track_id"])
            x = float(payload["x"])
            y = float(payload["y"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("sensor observation is malformed") from exc
        if not track_id or not (-1_000 <= x <= 1_000 and -1_000 <= y <= 1_000):
            raise ValueError("sensor observation is outside bounded coordinates")
        return Observation(
            self.source_id,
            self.channel_id,
            track_id,
            source_at,
            datetime.now(timezone.utc),
            x,
            y,
        )

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None
        if self._socket is not None:
            self._socket.close()
            self._socket = None


class ReplayAdapter:
    adapter_name = "fixture-replay"
    model_identity = "synthetic-fixture"

    def __init__(self, observations: Iterable[Observation]):
        self._observations = deque(observations)
        self.reconnect_count = 0

    def read(self) -> Observation:
        if not self._observations:
            raise EOFError("fixture replay is complete")
        return self._observations.popleft()

    def reconnect(self) -> None:
        self.reconnect_count += 1

    def close(self) -> None:
        return None

