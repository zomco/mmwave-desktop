"""Always-on acquisition loop with bounded reconnect policy."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from .acquisition import AcquisitionAdapter
from .clock import ClockHealth
from .detector import TraverseDetector
from .storage import GatewayStore


@dataclass(frozen=True, slots=True)
class ReconnectPolicy:
    initial_seconds: float = 0.25
    maximum_seconds: float = 30.0


class GatewayService:
    def __init__(
        self,
        adapter: AcquisitionAdapter,
        detector: TraverseDetector,
        clock: ClockHealth,
        store: GatewayStore,
        reconnect: ReconnectPolicy | None = None,
    ):
        self.adapter = adapter
        self.detector = detector
        self.clock = clock
        self.store = store
        self.reconnect = reconnect or ReconnectPolicy()

    def process_once(self) -> bool:
        observation = self.adapter.read()
        clock = self.clock.observe(observation)
        self.store.persist_observation(observation, clock)
        interval = self.detector.ingest(observation, clock)
        if interval:
            self.store.persist_interval(observation.source_id, interval)
            return True
        return False

    def run_forever(self, stop: threading.Event) -> None:
        delay = self.reconnect.initial_seconds
        while not stop.is_set():
            try:
                self.process_once()
                delay = self.reconnect.initial_seconds
            except (ConnectionError, TimeoutError, OSError, ValueError):
                self.adapter.close()
                if stop.wait(delay):
                    break
                delay = min(self.reconnect.maximum_seconds, max(delay * 2, self.reconnect.initial_seconds))
                try:
                    self.adapter.reconnect()
                except (ConnectionError, TimeoutError, OSError):
                    continue
            except EOFError:
                break
        self.adapter.close()

