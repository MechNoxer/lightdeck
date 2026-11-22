"""A simulated bridge so the app can be explored without hardware."""

from __future__ import annotations

import copy
import queue
import threading
import uuid
from typing import Any, Iterator

from .. import colors
from .util import deep_merge

Raw = dict[str, Any]


def _id() -> str:
    return str(uuid.uuid4())


def _state(on: bool = True, bri: float = 100, xy: tuple[float, float] | None = None, mirek: int | None = None) -> Raw:
    state: Raw = {"on": {"on": on}, "dimming": {"brightness": bri}}
    if xy:
        state["color"] = {"xy": {"x": xy[0], "y": xy[1]}}
    if mirek:
        state["color_temperature"] = {"mirek": mirek}
    return state


SUNSET = [(0.5916, 0.3824), (0.6425, 0.3297), (0.5269, 0.2559)]
AURORA = [(0.1797, 0.5547), (0.1532, 0.2061), (0.1747, 0.0839), (0.2648, 0.1037)]
TROPICAL = [(0.5578, 0.4157), (0.2108, 0.6164), (0.4442, 0.4876)]


class DemoClient:
    ip = "demo"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: queue.Queue[list[Raw]] = queue.Queue()
        self._res: dict[str, Raw] = {}
        self._build()

    # -- fixture -----------------------------------------------------------

    def _add(self, item: Raw) -> Raw:
        self._res[item["id"]] = item
        return item

    def _light(self, name: str, archetype: str, kind: str, state: Raw, reachable: bool = True) -> tuple[Raw, Raw]:
        device_id, light_id, zigbee_id = _id(), _id(), _id()
        light: Raw = {
            "id": light_id,
            "type": "light",
            "owner": {"rid": device_id, "rtype": "device"},
            "metadata": {"name": name, "archetype": archetype},
            "on": {"on": False},
            "dimming": {"brightness": 100.0, "min_dim_level": 0.2},
        }
        if kind in ("color", "ambiance"):
            light["color_temperature"] = {
                "mirek": 366, "mirek_valid": True,
                "mirek_schema": {"mirek_minimum": 153, "mirek_maximum": 500},
            }
        if kind == "color":
            light["color"] = {
                "xy": {"x": 0.4573, "y": 0.41},
                "gamut": {
                    "red": {"x": 0.6915, "y": 0.3083},
                    "green": {"x": 0.17, "y": 0.7},
                    "blue": {"x": 0.1532, "y": 0.0475},
                },
                "gamut_type": "C",
            }
        light = deep_merge(light, self._normalize(light, state))
        device = {
            "id": device_id, "type": "device",
            "metadata": {"name": name, "archetype": archetype},
            "services": [{"rid": light_id, "rtype": "light"}, {"rid": zigbee_id, "rtype": "zigbee_connectivity"}],
        }
        zigbee = {
            "id": zigbee_id, "type": "zigbee_connectivity",
            "owner": {"rid": device_id, "rtype": "device"},
            "status": "connected" if reachable else "connectivity_issue",
        }
        for item in (light, device, zigbee):
            self._add(item)
        return device, light

    def _group(self, kind: str, name: str, archetype: str, members: list[tuple[Raw, Raw]]) -> Raw:
        group_id, grouped_id = _id(), _id()
        if kind == "room":
            children = [{"rid": d["id"], "rtype": "device"} for d, _ in members]
        else:
            children = [{"rid": light["id"], "rtype": "light"} for _, light in members]
        self._add({
            "id": grouped_id, "type": "grouped_light",
            "owner": {"rid": group_id, "rtype": kind}, "on": {"on": False},
            "dimming": {"brightness": 100.0},
        })
        return self._add({
            "id": group_id, "type": kind,
            "metadata": {"name": name, "archetype": archetype},
            "children": children,
            "services": [{"rid": grouped_id, "rtype": "grouped_light"}],
        })

    def _scene(self, group: Raw, name: str, lights: list[Raw], states: list[Raw], active: bool = False) -> None:
        actions = []
        for index, light in enumerate(lights):
            state = states[index % len(states)]
            if "color" in state and "color" not in light:
                state = {k: v for k, v in state.items() if k != "color"} | {"color_temperature": {"mirek": 370}}
            if "color_temperature" in state and "color_temperature" not in light:
                state = {k: v for k, v in state.items() if k != "color_temperature"}
            actions.append({"target": {"rid": light["id"], "rtype": "light"}, "action": copy.deepcopy(state)})
        self._add({
            "id": _id(), "type": "scene",
            "metadata": {"name": name},
            "group": {"rid": group["id"], "rtype": group["type"]},
            "actions": actions,
            "status": {"active": "static" if active else "inactive"},
        })

    def _build(self) -> None:
        bridge_device = _id()
        self._add({"id": bridge_device, "type": "device", "metadata": {"name": "Demo Bridge", "archetype": "bridge_v2"},
                   "services": []})
        self._add({"id": _id(), "type": "bridge", "owner": {"rid": bridge_device, "rtype": "device"}})

        living = [
            self._light("Ceiling", "ceiling_round", "color", _state(True, 78, mirek=370)),
            self._light("Floor lamp", "floor_shade", "color", _state(True, 64, xy=SUNSET[0])),
            self._light("TV lightstrip", "hue_lightstrip_tv", "color", _state(True, 50, xy=SUNSET[2])),
            self._light("Reading lamp", "table_shade", "ambiance", _state(False, 100, mirek=300)),
        ]
        bedroom = [
            self._light("Bedside left", "table_round", "color", _state(True, 32, mirek=447)),
            self._light("Bedside right", "table_round", "color", _state(False, 32, mirek=447)),
        ]
        kitchen = [
            self._light("Pendant 1", "pendant_round", "ambiance", _state(True, 100, mirek=233)),
            self._light("Pendant 2", "pendant_round", "ambiance", _state(True, 100, mirek=233)),
            self._light("Under cabinet", "hue_lightstrip", "white", _state(False, 100), reachable=False),
        ]
        office = [self._light("Desk lamp", "desk_lamp", "color", _state(False, 80, mirek=233))]

        rooms = {
            "living": self._group("room", "Living room", "living_room", living),
            "bedroom": self._group("room", "Bedroom", "bedroom", bedroom),
            "kitchen": self._group("room", "Kitchen", "kitchen", kitchen),
            "office": self._group("room", "Office", "office", office),
        }
        zone = self._group("zone", "Downstairs", "downstairs", living + kitchen)
        home_grouped = _id()
        self._add({"id": home_grouped, "type": "grouped_light",
                   "owner": {"rid": "home", "rtype": "bridge_home"}, "on": {"on": True}})
        self._add({"id": "home", "type": "bridge_home", "children": [],
                   "services": [{"rid": home_grouped, "rtype": "grouped_light"}]})

        lights = lambda members: [light for _, light in members]  # noqa: E731
        relax, read = _state(True, 56, mirek=447), _state(True, 100, mirek=346)
        concentrate, energize = _state(True, 100, mirek=233), _state(True, 100, mirek=156)
        night = _state(True, 1, xy=(0.561, 0.4042))
        self._scene(rooms["living"], "Relax", lights(living), [relax])
        self._scene(rooms["living"], "Read", lights(living), [read])
        self._scene(rooms["living"], "Concentrate", lights(living), [concentrate])
        self._scene(rooms["living"], "Sunset", lights(living), [_state(True, 70, xy=xy) for xy in SUNSET], active=True)
        self._scene(rooms["living"], "Aurora", lights(living), [_state(True, 60, xy=xy) for xy in AURORA])
        self._scene(rooms["living"], "Nightlight", lights(living), [night])
        self._scene(rooms["bedroom"], "Relax", lights(bedroom), [relax])
        self._scene(rooms["bedroom"], "Tropical", lights(bedroom), [_state(True, 60, xy=xy) for xy in TROPICAL])
        self._scene(rooms["bedroom"], "Nightlight", lights(bedroom), [night])
        self._scene(rooms["kitchen"], "Energize", lights(kitchen), [energize])
        self._scene(rooms["kitchen"], "Dimmed", lights(kitchen), [_state(True, 30, mirek=370)])
        self._scene(rooms["office"], "Concentrate", lights(office), [concentrate])
        self._scene(rooms["office"], "Read", lights(office), [read])
        self._scene(zone, "Bright", lights(living + kitchen), [_state(True, 100, mirek=300)])
        self._sync_groups()

    # -- state logic -------------------------------------------------------

    @staticmethod
    def _normalize(light: Raw, state: Raw) -> Raw:
        update = {k: copy.deepcopy(v) for k, v in state.items() if k in ("on", "dimming", "color", "color_temperature")}
        if "color" in update and "color" not in light:
            del update["color"]
        if "color_temperature" in update:
            if "color_temperature" not in light:
                del update["color_temperature"]
            else:
                update["color_temperature"]["mirek_valid"] = True
                mirek = update["color_temperature"]["mirek"]
                if "color" in light:
                    update.setdefault("color", {})["xy"] = dict(zip("xy", colors.rgb_to_xy(*colors.mirek_to_rgb(mirek))))
        elif "color" in update and "color_temperature" in light:
            update["color_temperature"] = {"mirek": None, "mirek_valid": False}
        return update

    def _lights_of(self, owner: Raw | None) -> list[Raw]:
        if owner is None:
            return []
        if owner["type"] == "bridge_home":
            return [r for r in self._res.values() if r["type"] == "light"]
        result = []
        for child in owner.get("children", []):
            item = self._res.get(child["rid"])
            if not item:
                continue
            if item["type"] == "light":
                result.append(item)
            elif item["type"] == "device":
                result += [self._res[s["rid"]] for s in item["services"] if s["rtype"] == "light"]
        return result

    def _sync_groups(self) -> list[Raw]:
        updates = []
        for grouped in [r for r in self._res.values() if r["type"] == "grouped_light"]:
            members = self._lights_of(self._res.get(grouped["owner"]["rid"]))
            on = any(m["on"]["on"] for m in members if self._reachable(m))
            if grouped["on"]["on"] != on:
                grouped["on"]["on"] = on
                updates.append({"id": grouped["id"], "type": "grouped_light", "on": {"on": on}})
        return updates

    def _reachable(self, light: Raw) -> bool:
        device = self._res[light["owner"]["rid"]]
        zigbee = next(self._res[s["rid"]] for s in device["services"] if s["rtype"] == "zigbee_connectivity")
        return zigbee["status"] == "connected"

    def _apply_light(self, light: Raw, state: Raw) -> Raw | None:
        if not self._reachable(light):
            return None
        update = self._normalize(light, state)
        if not update:
            return None
        self._res[light["id"]] = deep_merge(light, update)
        return {"id": light["id"], "type": "light", **update}

    def _deactivate_scenes(self, light_ids: set[str]) -> list[Raw]:
        updates = []
        for scene in [r for r in self._res.values() if r["type"] == "scene"]:
            targets = {a["target"]["rid"] for a in scene["actions"]}
            if targets & light_ids and scene["status"]["active"] != "inactive":
                scene["status"]["active"] = "inactive"
                updates.append({"id": scene["id"], "type": "scene", "status": {"active": "inactive"}})
        return updates

    # -- client interface --------------------------------------------------

    def get_all(self) -> list[Raw]:
        with self._lock:
            return copy.deepcopy(list(self._res.values()))

    def put(self, rtype: str, rid: str, payload: Raw) -> None:
        with self._lock:
            target = self._res.get(rid)
            if target is None:
                from .client import HueError
                raise HueError(f"Resource {rid} not found.")
            updates: list[Raw] = []
            if rtype == "scene":
                if "recall" in payload:
                    light_ids = set()
                    for action in target["actions"]:
                        light = self._res.get(action["target"]["rid"])
                        if light and (update := self._apply_light(light, action["action"])):
                            updates.append(update)
                            light_ids.add(light["id"])
                    updates += self._deactivate_scenes(light_ids)
                    target["status"]["active"] = "static"
                    updates.append({"id": rid, "type": "scene", "status": {"active": "static"}})
                for key in ("metadata", "actions"):
                    if key in payload:
                        target[key] = copy.deepcopy(payload[key])
                        updates.append({"id": rid, "type": "scene", key: copy.deepcopy(payload[key])})
            elif rtype == "light":
                if update := self._apply_light(target, payload):
                    updates.append(update)
                    updates += self._deactivate_scenes({rid})
            elif rtype == "grouped_light":
                members = self._lights_of(self._res.get(target["owner"]["rid"]))
                for light in members:
                    if update := self._apply_light(light, payload):
                        updates.append(update)
                updates += self._deactivate_scenes({m["id"] for m in members})
            updates += self._sync_groups()
        if updates:
            self._events.put([{"type": "update", "data": updates}])

    def post(self, rtype: str, payload: Raw) -> str:
        with self._lock:
            rid = _id()
            item = copy.deepcopy(payload) | {"id": rid, "type": rtype}
            if rtype == "scene":
                item.setdefault("status", {"active": "inactive"})
            self._res[rid] = item
        self._events.put([{"type": "add", "data": [copy.deepcopy(item)]}])
        return rid

    def delete(self, rtype: str, rid: str) -> None:
        with self._lock:
            self._res.pop(rid, None)
        self._events.put([{"type": "delete", "data": [{"id": rid, "type": rtype}]}])

    def iter_events(self, stop: threading.Event) -> Iterator[list[Raw]]:
        yield []
        while not stop.is_set():
            try:
                yield self._events.get(timeout=0.25)
            except queue.Empty:
                continue

    def abort_events(self) -> None:
        pass
