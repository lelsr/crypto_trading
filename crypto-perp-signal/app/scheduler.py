"""Simple controlled loop scheduler for scan cycles."""

from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Any


@dataclass
class LoopScheduler:
    orchestrator: Any
    loop_minutes: int = 38
    sleep_func: Any = time.sleep

    def __post_init__(self) -> None:
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run_once(self):
        return self.orchestrator.run_once()

    def run_loop(self, *, max_cycles: int | None = None) -> int:
        completed = 0
        while not self._stop_event.is_set():
            self.orchestrator.run_once()
            completed += 1
            if max_cycles is not None and completed >= max_cycles:
                break
            self.sleep_func(self.loop_minutes * 60)
        return completed
