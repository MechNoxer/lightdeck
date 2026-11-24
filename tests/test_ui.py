"""End-to-end UI tests against the simulated bridge (runs headless)."""

from __future__ import annotations

import time

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

from lightdeck.config import AppConfig
from lightdeck.ui.main_window import MainWindow
from lightdeck.ui.scene_editor import SceneEditor
from lightdeck.ui.theme import ThemeManager


def wait_until(predicate, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QTest.qWait(20)
        if predicate():
            return
    raise AssertionError("condition not met in time")


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("LIGHTDECK_CONFIG_DIR", str(tmp_path))
    themes = ThemeManager(qapp, "dark")
    themes.apply()
    win = MainWindow(AppConfig(), themes, demo=True)
    win.resize(1280, 860)
    win.show()
    wait_until(lambda: win.controller.store.loaded and win.controller.connected)
    yield win
    win.close()


def living_room(win):
    return next(g for g in win.controller.store.groups("room") if g.name == "Living room")


def demo_state(win, light_id):
    return next(r for r in win.controller.client.get_all() if r["id"] == light_id)


def test_drag_light_slider_updates_bridge_without_rebuilding(window):
    group = living_room(window)
    window.navigate(group.id)
    QTest.qWait(50)
    light_id = group.light_ids[0]
    tile = window.room._light_tiles[light_id]
    slider = tile.slider

    y = slider.height() // 2
    QTest.mousePress(slider, Qt.LeftButton, pos=QPoint(slider.width() // 5, y))
    for x in range(slider.width() // 5, slider.width() - 10, 12):
        QTest.mouseMove(slider, QPoint(x, y))
        QTest.qWait(5)
    QTest.mouseRelease(slider, Qt.LeftButton, pos=QPoint(slider.width() - 10, y))

    target = slider.value()
    assert target > 90
    wait_until(lambda: demo_state(window, light_id)["dimming"]["brightness"] == target)
    # The same tile object is still in place: live updates no longer rebuild cards.
    assert window.room._light_tiles[light_id] is tile


def test_click_on_track_jumps(window):
    group = living_room(window)
    window.navigate(group.id)
    slider = window.room.brightness
    QTest.mouseClick(slider, Qt.LeftButton, pos=QPoint(slider.height() // 2 + 1, slider.height() // 2))
    assert slider.value() <= 3
    wait_until(lambda: all(
        demo_state(window, lid)["dimming"]["brightness"] <= 3
        for lid in group.light_ids if demo_state(window, lid)["on"]["on"]
    ))


def test_temperature_slider_is_warm_on_the_left(window):
    group = living_room(window)
    window.navigate(group.id)
    light_id = group.light_ids[0]
    window.room.panel.show_light(window.controller, light_id)
    temperature = window.room.panel.color.temperature
    sent = []
    temperature.mirekChanged.connect(sent.append)
    y = temperature.height() // 2
    QTest.mouseClick(temperature, Qt.LeftButton, pos=QPoint(2, y))
    QTest.mouseClick(temperature, Qt.LeftButton, pos=QPoint(temperature.width() - 2, y))
    assert sent[0] == 500 and sent[-1] == 153  # left = 2000 K warm, right = 6500 K cool


def test_scene_recall_and_create_and_delete(window):
    group = living_room(window)
    store = window.controller.store
    window.navigate(group.id)
    relax = next(s for s in store.scenes_for(group.id) if s.name == "Relax")
    window.controller.recall_scene(relax.id)
    wait_until(lambda: store.scene(relax.id).active)

    editor = SceneEditor(window.controller, group, None, window)
    editor.name.setText("Movie night")
    editor.rows[0].include.setChecked(False)
    editor.rows[1].set_color(xy=(0.2, 0.1))
    editor._save()
    wait_until(lambda: any(s.name == "Movie night" for s in store.scenes_for(group.id)))
    created = next(s for s in store.scenes_for(group.id) if s.name == "Movie night")
    assert len(created.actions) == len(group.light_ids) - 1
    assert created.id in window.room._scene_tiles

    window.controller.delete_scene(created.id)
    wait_until(lambda: store.scene(created.id) is None)
    wait_until(lambda: created.id not in window.room._scene_tiles)


def test_scene_preview_is_restored_on_cancel(window):
    group = living_room(window)
    light_id = group.light_ids[1]
    before = window.controller.store.light(light_id)
    editor = SceneEditor(window.controller, group, None, window)
    editor.preview.setChecked(True)
    editor._on_preview(True)
    editor.rows[1].set_color(xy=(0.17, 0.7))
    wait_until(lambda: abs(demo_state(window, light_id)["color"]["xy"]["x"] - 0.17) < 0.01)
    editor.reject()
    wait_until(lambda: abs(demo_state(window, light_id)["color"]["xy"]["x"] - before.xy[0]) < 0.01)


def test_room_toggle_and_all_off(window):
    group = living_room(window)
    window.navigate(group.id)
    QTest.mouseClick(window.room.toggle, Qt.LeftButton)
    wait_until(lambda: not any(demo_state(window, lid)["on"]["on"] for lid in group.light_ids))
    window.navigate("home")
    QTest.mouseClick(window.home.all_on, Qt.LeftButton)
    wait_until(lambda: window.home.subtitle.text().startswith("9 of 9"))
    QTest.mouseClick(window.home.all_off, Qt.LeftButton)
    wait_until(lambda: window.home.subtitle.text() == "All lights are off")


def test_theme_switch_and_exit_demo(window, monkeypatch):
    monkeypatch.setattr("lightdeck.ui.setup_page.discover_bridges", lambda: [])
    window.navigate("settings")
    window.settings.themeChanged.emit("light")
    assert window.config.theme == "light"
    window.forget_bridge()
    assert window.root.currentIndex() == window.SETUP
    assert window.controller is None


def test_closing_during_discovery_is_clean(qapp, tmp_path, monkeypatch):
    """Closing on the setup page while a network search is running must not crash."""
    from PySide6.QtCore import QThreadPool

    monkeypatch.setenv("LIGHTDECK_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr("lightdeck.ui.setup_page.discover_bridges", lambda: time.sleep(0.5) or [])
    themes = ThemeManager(qapp, "dark")
    win = MainWindow(AppConfig(), themes)
    win.show()
    QTest.qWait(50)
    win.close()
    win.shutdown()
    assert QThreadPool.globalInstance().waitForDone(3000)
