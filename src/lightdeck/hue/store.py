"""In-memory mirror of the bridge's resources, kept current by the event stream."""

from __future__ import annotations

import time
from typing import Any, Callable

from PySide6.QtCore import QObject, QTimer, Signal

from .models import GroupView, LightView, Raw, SceneView
from .util import deep_merge

# After a local change, ignore the bridge echoing intermediate values for
# this long so a slider being dragged doesn't jump back.
HOLD_SECONDS = 1.5
_STATE_KEYS = ("on", "dimming", "color", "color_temperature")


class Store(QObject):
    changed = Signal()

    def __init__(self, parent: QObject | None = None, clock: Callable[[], float] = time.monotonic) -> None:
        super().__init__(parent)
        self._resources: dict[str, Raw] = {}
        self._holds: dict[str, tuple[float, set[str]]] = {}
        self._clock = clock
        self._emit_pending = False
        self.loaded = False

    # -- mutation ----------------------------------------------------------

    def load(self, items: list[Raw]) -> None:
        self._resources = {item["id"]: item for item in items if "id" in item}
        self.loaded = True
        self._notify()

    def clear(self) -> None:
        self._resources.clear()
        self._holds.clear()
        self.loaded = False
        self._notify()

    def apply_events(self, events: list[dict[str, Any]]) -> None:
        now = self._clock()
        touched = False
        for event in events:
            kind = event.get("type")
            for item in event.get("data", []):
                rid = item.get("id")
                if not rid:
                    continue
                if kind == "delete":
                    touched |= self._resources.pop(rid, None) is not None
                elif kind == "add":
                    self._resources[rid] = item
                    touched = True
                elif kind == "update" and rid in self._resources:
                    hold = self._holds.get(rid)
                    if hold and hold[0] > now:
                        item = {k: v for k, v in item.items() if k not in hold[1]}
                    self._resources[rid] = deep_merge(self._resources[rid], item)
                    touched = True
        if touched:
            self._notify()

    def patch_local(self, rid: str, payload: Raw) -> None:
        """Optimistically apply a state change we're about to send."""
        current = self._resources.get(rid)
        if current is None:
            return
        state = {k: v for k, v in payload.items() if k in _STATE_KEYS}
        merged = deep_merge(current, state)
        if "color" in state and "color_temperature" in merged:
            merged["color_temperature"] = {**merged["color_temperature"], "mirek_valid": False}
        if "color_temperature" in state and "color_temperature" in merged:
            merged["color_temperature"] = {**merged["color_temperature"], "mirek_valid": True}
        self._resources[rid] = merged

        keys = set(state)
        if keys & {"color", "color_temperature"}:
            keys |= {"color", "color_temperature"}
        expiry = self._clock() + HOLD_SECONDS
        previous = self._holds.get(rid)
        if previous and previous[0] > self._clock():
            keys |= previous[1]
        self._holds[rid] = (expiry, keys)
        self._notify()

    def _notify(self) -> None:
        if self._emit_pending:
            return
        self._emit_pending = True
        QTimer.singleShot(0, self, self._emit_changed)

    def _emit_changed(self) -> None:
        self._emit_pending = False
        self.changed.emit()

    # -- queries -----------------------------------------------------------

    def raw(self, rid: str) -> Raw | None:
        return self._resources.get(rid)

    def of_type(self, rtype: str) -> list[Raw]:
        return [r for r in self._resources.values() if r.get("type") == rtype]

    def _service(self, raw: Raw, rtype: str) -> str | None:
        for ref in raw.get("services", []):
            if ref.get("rtype") == rtype:
                return ref.get("rid")
        return None

    def _reachable(self, light: Raw) -> bool:
        owner = self._resources.get((light.get("owner") or {}).get("rid", ""))
        if not owner:
            return True
        conn = self._resources.get(self._service(owner, "zigbee_connectivity") or "")
        if not conn:
            return True
        return conn.get("status", "connected") == "connected"

    def light(self, rid: str) -> LightView | None:
        raw = self._resources.get(rid)
        if not raw or raw.get("type") != "light":
            return None
        return LightView.from_raw(raw, self._reachable(raw))

    def lights(self) -> list[LightView]:
        result = [LightView.from_raw(r, self._reachable(r)) for r in self.of_type("light")]
        return sorted(result, key=lambda light: light.name.lower())

    def group(self, rid: str) -> GroupView | None:
        raw = self._resources.get(rid)
        if not raw or raw.get("type") not in ("room", "zone"):
            return None
        light_ids: list[str] = []
        for child in raw.get("children", []):
            if child.get("rtype") == "light":
                light_ids.append(child["rid"])
            elif child.get("rtype") == "device":
                device = self._resources.get(child["rid"])
                if device:
                    light_ids += [s["rid"] for s in device.get("services", []) if s.get("rtype") == "light"]
        light_ids = [lid for lid in dict.fromkeys(light_ids) if lid in self._resources]
        light_ids.sort(key=lambda lid: (self._resources[lid].get("metadata") or {}).get("name", "").lower())
        metadata = raw.get("metadata") or {}
        return GroupView(
            id=rid,
            kind=raw["type"],
            name=metadata.get("name", "Room"),
            archetype=metadata.get("archetype", ""),
            light_ids=tuple(light_ids),
            grouped_light_id=self._service(raw, "grouped_light"),
        )

    def groups(self, kind: str) -> list[GroupView]:
        result = [self.group(r["id"]) for r in self.of_type(kind)]
        return sorted((g for g in result if g), key=lambda g: g.name.lower())

    def group_lights(self, group: GroupView) -> list[LightView]:
        return [light for lid in group.light_ids if (light := self.light(lid))]

    def scenes_for(self, group_id: str) -> list[SceneView]:
        scenes = [SceneView.from_raw(r) for r in self.of_type("scene")]
        return sorted((s for s in scenes if s.group_id == group_id), key=lambda s: s.name.lower())

    def scene(self, rid: str) -> SceneView | None:
        raw = self._resources.get(rid)
        return SceneView.from_raw(raw) if raw and raw.get("type") == "scene" else None

    def home_grouped_light(self) -> str | None:
        for home in self.of_type("bridge_home"):
            rid = self._service(home, "grouped_light")
            if rid:
                return rid
        return None

    def bridge_name(self) -> str:
        for bridge in self.of_type("bridge"):
            owner = self._resources.get((bridge.get("owner") or {}).get("rid", ""))
            if owner:
                return (owner.get("metadata") or {}).get("name", "Hue Bridge")
        return "Hue Bridge"
