from __future__ import annotations

import json
import threading
import time

import pytest

from lightdeck import colors
from lightdeck.config import AppConfig, load_config, save_config
from lightdeck.hue.commands import CommandQueue
from lightdeck.hue.demo import DemoClient
from lightdeck.hue.models import LightView
from lightdeck.hue.util import merge_command


# -- colors -----------------------------------------------------------------

def test_mirek_kelvin_roundtrip():
    assert colors.mirek_to_kelvin(153) == 6536
    assert colors.mirek_to_kelvin(500) == 2000
    assert colors.kelvin_to_mirek(2000) == 500


def test_warm_is_redder_than_cool():
    warm, cool = colors.kelvin_to_rgb(2000), colors.kelvin_to_rgb(6500)
    assert warm[0] >= cool[0] and warm[2] < cool[2]


def test_hs_xy_roundtrip_stays_close():
    for hue in (0, 60, 120, 200, 280):
        x, y = colors.hs_to_xy(hue, 0.6)
        back_hue, back_sat = colors.xy_to_hs(x, y)
        assert min(abs(back_hue - hue), 360 - abs(back_hue - hue)) < 12
        assert abs(back_sat - 0.6) < 0.2


def test_clamp_to_gamut():
    outside = (0.8, 0.2)
    clamped = colors.clamp_to_gamut(outside, colors.GAMUT_C)
    assert colors.in_gamut(clamped, colors.GAMUT_C) or min(
        abs(clamped[0] - 0.6915), abs(clamped[1] - 0.3083)
    ) < 0.05
    inside = (0.4, 0.4)
    assert colors.clamp_to_gamut(inside) == inside


# -- config -----------------------------------------------------------------

def test_config_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    save_config(AppConfig(bridge_ip="10.0.0.2", app_key="k", theme="dark"), path)
    loaded = load_config(path, legacy_path=None)
    assert loaded.bridge_ip == "10.0.0.2" and loaded.theme == "dark" and loaded.is_paired


def test_legacy_config_is_migrated(tmp_path):
    legacy = tmp_path / "legacy.json"
    legacy.write_text(json.dumps({"bridge_ip": "10.0.0.9", "username": "abc"}))
    path = tmp_path / "new" / "config.json"
    loaded = load_config(path, legacy_path=legacy)
    assert loaded.app_key == "abc" and loaded.bridge_ip == "10.0.0.9"
    assert path.exists()


# -- commands ---------------------------------------------------------------

def test_merge_command_color_and_ct_are_exclusive():
    merged = merge_command({"color_temperature": {"mirek": 300}, "on": {"on": True}}, {"color": {"xy": {"x": 0.3, "y": 0.3}}})
    assert "color_temperature" not in merged and merged["on"] == {"on": True}


class RecordingClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict, float]] = []

    def put(self, rtype, rid, payload):
        self.calls.append((rtype, rid, payload, time.monotonic()))


def test_command_queue_coalesces_rapid_updates():
    client = RecordingClient()
    queue = CommandQueue(client, on_error=lambda exc: None)
    queue.start()
    try:
        for value in range(1, 41):
            queue.submit("light", "a", {"dimming": {"brightness": value}})
            time.sleep(0.005)
        deadline = time.monotonic() + 2
        while not queue.idle() and time.monotonic() < deadline:
            time.sleep(0.02)
        time.sleep(0.05)
    finally:
        queue.stop()
    assert client.calls[-1][2]["dimming"]["brightness"] == 40
    assert len(client.calls) < 10
    gaps = [b[3] - a[3] for a, b in zip(client.calls, client.calls[1:])]
    assert all(gap >= 0.09 for gap in gaps)


# -- demo + store -----------------------------------------------------------

def test_demo_resources_produce_views(qapp):
    from lightdeck.hue.store import Store

    client = DemoClient()
    store = Store()
    store.load(client.get_all())
    rooms = store.groups("room")
    assert [r.name for r in rooms] == ["Bedroom", "Kitchen", "Living room", "Office"]
    living = next(r for r in rooms if r.name == "Living room")
    assert len(living.light_ids) == 4 and living.grouped_light_id
    assert {s.name for s in store.scenes_for(living.id)} >= {"Relax", "Sunset"}
    unreachable = [l for l in store.lights() if not l.reachable]
    assert [l.name for l in unreachable] == ["Under cabinet"]


def test_demo_scene_recall_emits_events(qapp):
    from lightdeck.hue.store import Store

    client = DemoClient()
    store = Store()
    store.load(client.get_all())
    living = next(r for r in store.groups("room") if r.name == "Living room")
    relax = next(s for s in store.scenes_for(living.id) if s.name == "Relax")
    client.put("scene", relax.id, {"recall": {"action": "active"}})
    stop = threading.Event()
    events = client.iter_events(stop)
    assert next(events) == []
    store.apply_events(next(events))
    stop.set()
    lights = store.group_lights(living)
    assert all(l.on and l.mode == "ct" and l.mirek == 447 for l in lights)
    assert store.scene(relax.id).active
    assert not next(s for s in store.scenes_for(living.id) if s.name == "Sunset").active


def test_store_hold_ignores_stale_echo(qapp):
    from lightdeck.hue.store import Store

    now = [100.0]
    store = Store(clock=lambda: now[0])
    store.load([{"id": "l1", "type": "light", "on": {"on": True}, "dimming": {"brightness": 10.0}}])
    store.patch_local("l1", {"dimming": {"brightness": 80.0}})
    store.apply_events([{"type": "update", "data": [{"id": "l1", "dimming": {"brightness": 40.0}}]}])
    assert store.light("l1").brightness == 80.0
    now[0] += 5
    store.apply_events([{"type": "update", "data": [{"id": "l1", "dimming": {"brightness": 40.0}}]}])
    assert store.light("l1").brightness == 40.0


def test_light_mode_detection():
    base = {"id": "x", "type": "light", "on": {"on": True}, "dimming": {"brightness": 50},
            "color": {"xy": {"x": 0.5, "y": 0.4}},
            "color_temperature": {"mirek": None, "mirek_valid": False, "mirek_schema": {"mirek_minimum": 153, "mirek_maximum": 454}}}
    assert LightView.from_raw(base).mode == "color"
    base["color_temperature"] = {**base["color_temperature"], "mirek": 300, "mirek_valid": True}
    view = LightView.from_raw(base)
    assert view.mode == "ct" and view.mirek_max == 454


# -- client -----------------------------------------------------------------

def test_client_error_mapping(monkeypatch):
    from lightdeck.hue import client as client_mod

    class FakeResponse:
        def __init__(self, status, payload):
            self.status_code, self._payload = status, payload

        def json(self):
            return self._payload

    class FakeSession:
        def __init__(self, response):
            self.response = response

        def request(self, *args, **kwargs):
            return self.response

    send = client_mod.HueClient._send
    with pytest.raises(client_mod.HueUnauthorizedError):
        send(FakeSession(FakeResponse(403, {"errors": [{"description": "unauthorized"}]})), "get", "u")
    with pytest.raises(client_mod.HueError, match="bad thing"):
        send(FakeSession(FakeResponse(400, {"errors": [{"description": "bad thing"}], "data": []})), "put", "u")
    assert send(FakeSession(FakeResponse(200, {"errors": [], "data": [1]})), "get", "u") == {"errors": [], "data": [1]}

    monkeypatch.setattr(client_mod.HueClient, "_make_session", staticmethod(
        lambda fp: FakeSession(FakeResponse(200, [{"error": {"type": 101, "description": "link button not pressed"}}]))
    ))
    with pytest.raises(client_mod.LinkButtonNotPressedError):
        client_mod.HueClient.pair("1.2.3.4", "ff", "lightdeck#test")
