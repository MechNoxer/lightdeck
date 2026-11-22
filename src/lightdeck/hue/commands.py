"""Background sender that coalesces and rate-limits light commands.

Dragging a slider produces dozens of values per second; the bridge handles
roughly 10 light commands/s and 1 group command/s. Pending commands for the
same resource are merged, so only the latest value is sent when a slot opens.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Protocol

from .util import merge_command

MIN_INTERVAL = {"light": 0.1, "grouped_light": 0.5}
GLOBAL_INTERVAL = 0.06


class SupportsPut(Protocol):
    def put(self, rtype: str, rid: str, payload: dict[str, Any]) -> None: ...


class CommandQueue:
    def __init__(self, client: SupportsPut, on_error: Callable[[Exception], None]) -> None:
        self._client = client
        self._on_error = on_error
        self._cond = threading.Condition()
        self._pending: dict[tuple[str, str], dict[str, Any]] = {}
        self._last_sent: dict[tuple[str, str], float] = {}
        self._last_any = 0.0
        self._stopped = False
        self._thread = threading.Thread(target=self._run, name="hue-commands", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        with self._cond:
            self._stopped = True
            self._cond.notify_all()

    def submit(self, rtype: str, rid: str, payload: dict[str, Any]) -> None:
        key = (rtype, rid)
        with self._cond:
            self._pending[key] = merge_command(self._pending.get(key, {}), payload)
            self._cond.notify_all()

    def idle(self) -> bool:
        with self._cond:
            return not self._pending

    def _ready_at(self, key: tuple[str, str]) -> float:
        interval = MIN_INTERVAL.get(key[0], 0.1)
        return max(self._last_sent.get(key, 0.0) + interval, self._last_any + GLOBAL_INTERVAL)

    def _run(self) -> None:
        while True:
            with self._cond:
                while not self._stopped and not self._pending:
                    self._cond.wait()
                if self._stopped:
                    return
                key = min(self._pending, key=self._ready_at)
                delay = self._ready_at(key) - time.monotonic()
                if delay > 0:
                    self._cond.wait(delay)
                    continue
                payload = self._pending.pop(key)
                now = time.monotonic()
                self._last_sent[key] = now
                self._last_any = now
            try:
                self._client.put(key[0], key[1], payload)
            except Exception as exc:  # noqa: BLE001
                self._on_error(exc)
