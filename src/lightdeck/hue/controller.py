"""Glue between a bridge client, the resource store and the UI thread."""

from __future__ import annotations

import threading
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThread, QThreadPool, Signal

from .client import CertificateMismatchError, HueError, HueUnauthorizedError
from .commands import CommandQueue
from .models import GroupView, Raw
from .store import Store


class _TaskSignals(QObject):
    done = Signal(object)
    failed = Signal(object)


class _Task(QRunnable):
    def __init__(self, fn: Callable[[], Any]) -> None:
        super().__init__()
        self.fn = fn
        self.signals = _TaskSignals()

    def run(self) -> None:
        try:
            result = self.fn()
        except Exception as exc:  # noqa: BLE001
            self.signals.failed.emit(exc)
            return
        self.signals.done.emit(result)


class TaskRunner(QObject):
    """Runs blocking calls on the thread pool, delivering results on the UI thread."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._pool = QThreadPool.globalInstance()
        self._live: set[_Task] = set()

    def run(
        self,
        fn: Callable[[], Any],
        on_done: Callable[[Any], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        task = _Task(fn)
        task.setAutoDelete(False)
        self._live.add(task)

        def finish(result: Any) -> None:
            self._live.discard(task)
            if on_done:
                on_done(result)

        def fail(exc: Exception) -> None:
            self._live.discard(task)
            if on_error:
                on_error(exc)

        task.signals.done.connect(finish)
        task.signals.failed.connect(fail)
        self._pool.start(task)


class EventStream(QThread):
    events = Signal(list)
    connected = Signal(bool)
    failed = Signal(object)

    def __init__(self, client: Any, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._client = client
        self._stop = threading.Event()

    def run(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            try:
                for batch in self._client.iter_events(self._stop):
                    if not batch:
                        self.connected.emit(True)
                        backoff = 1.0
                    else:
                        self.events.emit(batch)
                    if self._stop.is_set():
                        return
            except (HueUnauthorizedError, CertificateMismatchError) as exc:
                self.connected.emit(False)
                self.failed.emit(exc)
                return
            except Exception:  # noqa: BLE001 - reconnect on anything else
                pass
            if self._stop.is_set():
                return
            self.connected.emit(False)
            self._stop.wait(backoff)
            backoff = min(backoff * 2, 30.0)

    def stop(self) -> None:
        self._stop.set()
        self._client.abort_events()
        if not self.wait(1500):
            # Still busy (e.g. mid-connect). Destroying a running QThread aborts
            # the process, so detach it and let it finish on its own.
            self.setParent(None)
            _lingering_threads.append(self)


_lingering_threads: list[EventStream] = []


def wait_for_background_threads(timeout_ms: int = 8000) -> None:
    """Call before exiting so no QThread is destroyed while still running."""
    for thread in _lingering_threads:
        thread.wait(timeout_ms)
    _lingering_threads.clear()


class HueController(QObject):
    loaded = Signal()
    connectionChanged = Signal(bool)
    error = Signal(str)
    unauthorized = Signal()
    _commandError = Signal(object)

    def __init__(self, client: Any, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.client = client
        self.store = Store(self)
        self.tasks = TaskRunner(self)
        self.commands = CommandQueue(client, self._commandError.emit)
        self._commandError.connect(self._handle_error)
        self._stream: EventStream | None = None
        self._connected = False
        self._ever_connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        self.commands.start()
        self.reload()
        self._stream = EventStream(self.client, self)
        self._stream.events.connect(self.store.apply_events)
        self._stream.connected.connect(self._on_stream_connected)
        self._stream.failed.connect(self._handle_error)
        self._stream.start()

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream = None
        self.commands.stop()

    def reload(self) -> None:
        def done(items: list[Raw]) -> None:
            self.store.load(items)
            self.loaded.emit()

        self.tasks.run(self.client.get_all, done, self._handle_error)

    def _on_stream_connected(self, connected: bool) -> None:
        if connected and self._ever_connected and not self._connected:
            self.reload()  # catch up on anything missed while disconnected
        self._ever_connected |= connected
        if connected != self._connected:
            self._connected = connected
            self.connectionChanged.emit(connected)

    def _handle_error(self, exc: Exception) -> None:
        if isinstance(exc, HueUnauthorizedError):
            self.unauthorized.emit()
        elif isinstance(exc, HueError):
            self.error.emit(str(exc))
        else:
            self.error.emit(f"Unexpected error: {exc}")

    # -- light control -----------------------------------------------------

    @staticmethod
    def build_state(
        *,
        on: bool | None = None,
        brightness: float | None = None,
        xy: tuple[float, float] | None = None,
        mirek: int | None = None,
    ) -> Raw:
        payload: Raw = {}
        if brightness is not None:
            payload["dimming"] = {"brightness": round(max(1.0, min(100.0, brightness)), 1)}
        if xy is not None:
            payload["color"] = {"xy": {"x": round(xy[0], 4), "y": round(xy[1], 4)}}
        if mirek is not None:
            payload["color_temperature"] = {"mirek": int(mirek)}
        if on is not None:
            payload["on"] = {"on": on}
        elif payload:
            payload["on"] = {"on": True}  # adjusting a light implies turning it on
        return payload

    def set_light(self, light_id: str, **state: Any) -> None:
        payload = self.build_state(**state)
        if not payload:
            return
        self.store.patch_local(light_id, payload)
        self.commands.submit("light", light_id, payload)

    def set_group(self, group: GroupView, *, on: bool | None = None, brightness: float | None = None) -> None:
        payload = self.build_state(on=on, brightness=brightness)
        if not payload:
            return
        for light_id in group.light_ids:
            self.store.patch_local(light_id, payload)
        if group.grouped_light_id:
            self.store.patch_local(group.grouped_light_id, payload)
            self.commands.submit("grouped_light", group.grouped_light_id, payload)
        else:
            for light_id in group.light_ids:
                self.commands.submit("light", light_id, payload)

    def set_all(self, on: bool) -> None:
        payload = self.build_state(on=on)
        for light in self.store.lights():
            self.store.patch_local(light.id, payload)
        home = self.store.home_grouped_light()
        if home:
            self.commands.submit("grouped_light", home, payload)
        else:
            for light in self.store.lights():
                self.commands.submit("light", light.id, payload)

    # -- scenes ------------------------------------------------------------

    def recall_scene(self, scene_id: str) -> None:
        raw = self.store.raw(scene_id)
        if not raw:
            return
        for entry in raw.get("actions", []):
            target = (entry.get("target") or {}).get("rid")
            if target:
                self.store.patch_local(target, entry.get("action", {}))
        self.tasks.run(
            lambda: self.client.put("scene", scene_id, {"recall": {"action": "active"}}),
            on_error=self._handle_error,
        )

    def save_scene(
        self,
        scene_id: str | None,
        name: str,
        group: GroupView,
        actions: list[Raw],
        on_done: Callable[[], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        payload: Raw = {"metadata": {"name": name[:32]}, "actions": actions}
        if scene_id is None:
            payload["type"] = "scene"
            payload["group"] = {"rid": group.id, "rtype": group.kind}
            fn = lambda: self.client.post("scene", payload)  # noqa: E731
        else:
            fn = lambda: self.client.put("scene", scene_id, payload)  # noqa: E731
        self.tasks.run(
            fn,
            lambda _: on_done and on_done(),
            lambda exc: on_error(str(exc)) if on_error else self._handle_error(exc),
        )

    def delete_scene(self, scene_id: str, on_done: Callable[[], None] | None = None) -> None:
        self.tasks.run(
            lambda: self.client.delete("scene", scene_id),
            lambda _: on_done and on_done(),
            self._handle_error,
        )
