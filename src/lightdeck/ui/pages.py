"""Home overview, room detail (with light drawer) and settings."""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME, __version__
from ..hue.controller import HueController
from ..hue.models import GroupView
from .color_controls import ColorControls
from .scene_editor import SceneEditor
from .tiles import AddSceneTile, LightTile, RoomCard, SceneTile, brightness_fill
from .widgets import (
    muted_fill,
    PillSlider,
    ResponsiveGrid,
    Segmented,
    ToggleSwitch,
    button,
    icon_button,
    label,
)


def _scroll(content: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    area.setWidget(content)
    return area


def _page_content() -> tuple[QWidget, QVBoxLayout]:
    content = QWidget()
    layout = QVBoxLayout(content)
    layout.setContentsMargins(36, 30, 36, 36)
    layout.setSpacing(14)
    return content, layout


def _section_header(title: str, trailing: QWidget | None = None) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setContentsMargins(0, 14, 0, 0)
    row.addWidget(label(title, "SectionTitle"))
    row.addStretch(1)
    if trailing is not None:
        row.addWidget(trailing)
    return row


def _sync_tiles(grid: ResponsiveGrid, existing: dict, ids: list[str], create: Callable, update: Callable) -> None:
    """Create/update/remove tiles in place so live updates never rebuild the page."""
    changed = list(existing) != ids
    for rid in list(existing):
        if rid not in ids:
            existing.pop(rid)
    for rid in ids:
        if rid not in existing:
            existing[rid] = create(rid)
            changed = True
        update(existing[rid], rid)
    if changed:
        grid.set_widgets([existing[rid] for rid in ids])


def _greeting() -> str:
    hour = datetime.now().hour
    return "Good morning" if 5 <= hour < 12 else "Good afternoon" if hour < 18 else "Good evening"


# ---------------------------------------------------------------------------
# Home
# ---------------------------------------------------------------------------

class HomePage(QWidget):
    openGroup = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller: HueController | None = None
        self._room_cards: dict[str, RoomCard] = {}
        self._zone_cards: dict[str, RoomCard] = {}

        content, layout = _page_content()
        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        self.title = label(_greeting(), "PageTitle")
        self.subtitle = label("", "PageSubtitle")
        titles.addWidget(self.title)
        titles.addWidget(self.subtitle)
        header.addLayout(titles, 1)
        self.all_on = button("All on")
        self.all_off = button("All off", "Primary", "moon")
        self.all_on.clicked.connect(lambda: self.controller and self.controller.set_all(True))
        self.all_off.clicked.connect(lambda: self.controller and self.controller.set_all(False))
        header.addWidget(self.all_on, 0, Qt.AlignVCenter)
        header.addWidget(self.all_off, 0, Qt.AlignVCenter)
        layout.addLayout(header)

        layout.addLayout(_section_header("Rooms"))
        self.rooms = ResponsiveGrid(260, 14)
        layout.addWidget(self.rooms)
        self.empty = label("No rooms yet. Rooms you create in the Hue app show up here.", "Muted", True)
        layout.addWidget(self.empty)
        self.zones_header = QWidget()
        self.zones_header.setLayout(_section_header("Zones"))
        self.zones_header.layout().setContentsMargins(0, 14, 0, 0)
        layout.addWidget(self.zones_header)
        self.zones = ResponsiveGrid(260, 14)
        layout.addWidget(self.zones)
        layout.addStretch(1)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(_scroll(content))

    def set_controller(self, controller: HueController | None) -> None:
        self.controller = controller
        for cards, grid in ((self._room_cards, self.rooms), (self._zone_cards, self.zones)):
            cards.clear()
            grid.set_widgets([])

    def _make_card(self, rid: str) -> RoomCard:
        store = self.controller.store
        card = RoomCard(store.group(rid))
        card.opened.connect(self.openGroup.emit)
        card.powerToggled.connect(lambda gid, on: self._group_action(gid, on=on))
        card.brightnessChanged.connect(lambda gid, v: self._group_action(gid, brightness=v))
        return card

    def _group_action(self, group_id: str, **kwargs) -> None:
        group = self.controller.store.group(group_id) if self.controller else None
        if group:
            self.controller.set_group(group, **kwargs)

    def refresh(self) -> None:
        if not self.controller:
            return
        store = self.controller.store
        self.title.setText(_greeting())
        lights = [l for l in store.lights() if l.reachable]
        lit = sum(1 for l in lights if l.on)
        self.subtitle.setText(
            "All lights are off" if lights and not lit
            else f"{lit} of {len(lights)} lights on" if lights else "Loading…" if not store.loaded else "No lights found"
        )
        self.all_on.setEnabled(lit < len(lights))
        self.all_off.setEnabled(lit > 0)

        def update(card: RoomCard, rid: str) -> None:
            group = store.group(rid)
            card.update_group(group, store.group_lights(group))

        rooms = [g.id for g in store.groups("room")]
        zones = [g.id for g in store.groups("zone")]
        _sync_tiles(self.rooms, self._room_cards, rooms, self._make_card, update)
        _sync_tiles(self.zones, self._zone_cards, zones, self._make_card, update)
        self.empty.setVisible(store.loaded and not rooms)
        self.zones_header.setVisible(bool(zones))
        self.zones.setVisible(bool(zones))


# ---------------------------------------------------------------------------
# Light drawer
# ---------------------------------------------------------------------------

class LightPanel(QFrame):
    closed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Drawer")
        self.setFixedWidth(340)
        self.controller: HueController | None = None
        self.light_id: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 24)
        layout.setSpacing(16)
        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        self.title = label("", "PanelTitle")
        self.meta = label("", "CardMeta")
        titles.addWidget(self.title)
        titles.addWidget(self.meta)
        header.addLayout(titles, 1)
        close = icon_button("close", "Close")
        close.clicked.connect(self.closed.emit)
        header.addWidget(close, 0, Qt.AlignTop)
        layout.addLayout(header)

        power = QHBoxLayout()
        power.addWidget(label("Power", "FieldLabel"))
        power.addStretch(1)
        self.toggle = ToggleSwitch()
        self.toggle.toggled.connect(lambda on: self._send(on=on))
        power.addWidget(self.toggle)
        layout.addLayout(power)

        self.brightness_label = label("Brightness", "FieldLabel")
        layout.addWidget(self.brightness_label)
        self.brightness = PillSlider(height=44)
        self.brightness.valueChanged.connect(lambda v: self._send(brightness=v))
        layout.addWidget(self.brightness)

        self.color = ColorControls(wheel_size=264)
        self.color.xyChanged.connect(lambda x, y: self._send(xy=(x, y)))
        self.color.mirekChanged.connect(lambda m: self._send(mirek=m))
        layout.addSpacing(4)
        layout.addWidget(self.color)
        layout.addStretch(1)

    def _send(self, **state) -> None:
        if self.controller and self.light_id:
            self.controller.set_light(self.light_id, **state)

    def show_light(self, controller: HueController, light_id: str) -> None:
        self.controller = controller
        self.light_id = light_id
        light = controller.store.light(light_id)
        if light is None:
            return
        self.color.configure(
            has_color=light.has_color, has_ct=light.has_ct, gamut=light.gamut,
            mirek_min=light.mirek_min, mirek_max=light.mirek_max,
        )
        self.refresh()
        self.show()

    def refresh(self) -> None:
        if not (self.controller and self.light_id):
            return
        light = self.controller.store.light(self.light_id)
        if light is None:
            self.closed.emit()
            return
        self.title.setText(light.name)
        self.meta.setText(
            "Unreachable — check that it's powered" if not light.reachable
            else ("Color" if light.mode == "color" else "White" if light.mode == "ct" else "Dimmable")
            + (" · Off" if not light.on else "")
        )
        self.toggle.setChecked(light.on)
        for widget in (self.toggle, self.brightness, self.color):
            widget.setEnabled(light.reachable)
        self.brightness.setVisible(light.has_dimming)
        self.brightness_label.setVisible(light.has_dimming)
        self.brightness.setValue(round(light.brightness))
        self.brightness.setFillColor(brightness_fill(light.rgb))
        self.color.set_state(light.mode, light.xy, light.mirek)


# ---------------------------------------------------------------------------
# Room
# ---------------------------------------------------------------------------

class RoomPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller: HueController | None = None
        self.group_id: str | None = None
        self._scene_tiles: dict[str, QWidget] = {}
        self._light_tiles: dict[str, LightTile] = {}

        content, layout = _page_content()
        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        self.title = label("", "PageTitle")
        self.subtitle = label("", "PageSubtitle")
        titles.addWidget(self.title)
        titles.addWidget(self.subtitle)
        header.addLayout(titles, 1)
        self.toggle = ToggleSwitch()
        self.toggle.toggled.connect(lambda on: self._group(on=on))
        header.addWidget(self.toggle, 0, Qt.AlignVCenter)
        layout.addLayout(header)
        self.brightness = PillSlider(height=48)
        self.brightness.valueChanged.connect(lambda v: self._group(brightness=v))
        layout.addSpacing(6)
        layout.addWidget(self.brightness)

        layout.addLayout(_section_header("Scenes"))
        self.scenes = ResponsiveGrid(168, 12)
        layout.addWidget(self.scenes)
        layout.addLayout(_section_header("Lights"))
        self.lights = ResponsiveGrid(250, 14)
        layout.addWidget(self.lights)
        layout.addStretch(1)

        self.panel = LightPanel()
        self.panel.hide()
        self.panel.closed.connect(self.close_panel)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(_scroll(content), 1)
        outer.addWidget(self.panel)

    def set_controller(self, controller: HueController | None) -> None:
        self.controller = controller
        self.group_id = None
        self._reset()

    def _reset(self) -> None:
        self._scene_tiles.clear()
        self._light_tiles.clear()
        self.scenes.set_widgets([])
        self.lights.set_widgets([])
        self.close_panel()

    def show_group(self, group_id: str) -> None:
        if group_id != self.group_id:
            self.group_id = group_id
            self._reset()
        self.refresh()

    def close_panel(self) -> None:
        self.panel.hide()
        self.panel.light_id = None

    def _current_group(self) -> GroupView | None:
        return self.controller.store.group(self.group_id) if self.controller and self.group_id else None

    def _group(self, **kwargs) -> None:
        group = self._current_group()
        if group:
            self.controller.set_group(group, **kwargs)

    # -- tiles -------------------------------------------------------------

    def _make_light_tile(self, rid: str) -> LightTile:
        tile = LightTile(self.controller.store.light(rid))
        tile.powerToggled.connect(lambda lid, on: self.controller.set_light(lid, on=on))
        tile.brightnessChanged.connect(lambda lid, v: self.controller.set_light(lid, brightness=v))
        tile.opened.connect(lambda lid: self.panel.show_light(self.controller, lid))
        return tile

    def _make_scene_tile(self, rid: str) -> QWidget:
        if rid == "__add__":
            tile = AddSceneTile()
            tile.clicked.connect(lambda: self._edit_scene(None))
            return tile
        tile = SceneTile(self.controller.store.scene(rid))
        tile.activated.connect(self.controller.recall_scene)
        tile.editRequested.connect(self._edit_scene)
        tile.deleteRequested.connect(self._delete_scene)
        return tile

    def _edit_scene(self, scene_id: str | None) -> None:
        group = self._current_group()
        if not group:
            return
        scene = self.controller.store.scene(scene_id) if scene_id else None
        SceneEditor(self.controller, group, scene, self.window()).exec()

    def _delete_scene(self, scene_id: str) -> None:
        scene = self.controller.store.scene(scene_id)
        if not scene:
            return
        answer = QMessageBox.question(
            self.window(), "Delete scene", f"Delete the scene “{scene.name}”? This removes it from the bridge.",
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel,
        )
        if answer == QMessageBox.Yes:
            self.controller.delete_scene(scene_id)

    def refresh(self) -> None:
        group = self._current_group()
        if group is None:
            return
        store = self.controller.store
        lights = store.group_lights(group)
        reachable = [l for l in lights if l.reachable]
        lit = [l for l in reachable if l.on]
        self.title.setText(group.name)
        kind = "Zone" if group.kind == "zone" else "Room"
        self.subtitle.setText(
            f"{kind} · " + (f"{len(lit)} of {len(lights)} lights on" if lit else f"{len(lights)} lights, all off")
        )
        self.toggle.setChecked(bool(lit))
        self.toggle.setEnabled(bool(reachable))
        self.brightness.setEnabled(bool(reachable))
        if lit:
            self.brightness.setValue(round(sum(l.brightness for l in lit) / len(lit)))
            self.brightness.setFillColor(brightness_fill(lit[0].rgb))
        else:
            self.brightness.setFillColor(muted_fill())

        scene_ids = [s.id for s in store.scenes_for(group.id)] + ["__add__"]
        _sync_tiles(
            self.scenes, self._scene_tiles, scene_ids, self._make_scene_tile,
            lambda tile, rid: rid != "__add__" and tile.update_scene(store.scene(rid)),
        )
        _sync_tiles(
            self.lights, self._light_tiles, [l.id for l in lights], self._make_light_tile,
            lambda tile, rid: tile.update_light(store.light(rid)),
        )
        if self.panel.isVisible():
            if self.panel.light_id in group.light_ids:
                self.panel.refresh()
            else:
                self.close_panel()


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

class SettingsPage(QWidget):
    themeChanged = Signal(str)
    forgetRequested = Signal()
    reconnectRequested = Signal()

    THEMES = ["system", "light", "dark"]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        content, layout = _page_content()
        layout.addWidget(label("Settings", "PageTitle"))
        layout.addSpacing(8)

        bridge = QFrame()
        bridge.setObjectName("Panel")
        bridge_layout = QVBoxLayout(bridge)
        bridge_layout.setContentsMargins(20, 18, 20, 20)
        bridge_layout.setSpacing(6)
        bridge_layout.addWidget(label("Bridge", "SectionTitle"))
        self.bridge_name = label("", "CardTitle")
        self.bridge_details = label("", "Muted", True)
        self.bridge_details.setTextInteractionFlags(Qt.TextSelectableByMouse)
        bridge_layout.addSpacing(6)
        bridge_layout.addWidget(self.bridge_name)
        bridge_layout.addWidget(self.bridge_details)
        actions = QHBoxLayout()
        actions.setContentsMargins(0, 12, 0, 0)
        self.reconnect = button("Reload")
        self.reconnect.clicked.connect(self.reconnectRequested.emit)
        self.forget = button("Forget bridge", "Danger", "unlink")
        self.forget.clicked.connect(self._confirm_forget)
        actions.addWidget(self.reconnect)
        actions.addWidget(self.forget)
        actions.addStretch(1)
        bridge_layout.addLayout(actions)
        layout.addWidget(bridge)

        appearance = QFrame()
        appearance.setObjectName("Panel")
        appearance_layout = QVBoxLayout(appearance)
        appearance_layout.setContentsMargins(20, 18, 20, 20)
        appearance_layout.setSpacing(12)
        appearance_layout.addWidget(label("Appearance", "SectionTitle"))
        self.theme = Segmented(["System", "Light", "Dark"])
        self.theme.changed.connect(lambda i: self.themeChanged.emit(self.THEMES[i]))
        appearance_layout.addWidget(self.theme)
        layout.addWidget(appearance)

        about = QFrame()
        about.setObjectName("Panel")
        about_layout = QVBoxLayout(about)
        about_layout.setContentsMargins(20, 18, 20, 20)
        about_layout.addWidget(label("About", "SectionTitle"))
        about_layout.addWidget(label(
            f"{APP_NAME} {__version__} — an independent desktop remote for Hue-compatible lights. "
            "Not affiliated with or endorsed by Signify or Philips.", "Muted", True))
        layout.addWidget(about)
        layout.addStretch(1)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(_scroll(content))

    def _confirm_forget(self) -> None:
        answer = QMessageBox.question(
            self.window(), "Forget bridge",
            "Disconnect from this bridge? You'll need to press its link button to pair again.",
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel,
        )
        if answer == QMessageBox.Yes:
            self.forgetRequested.emit()

    def set_theme(self, mode: str) -> None:
        self.theme.set_index(self.THEMES.index(mode) if mode in self.THEMES else 0)

    def set_bridge(self, name: str, details: str, demo: bool) -> None:
        self.bridge_name.setText(name)
        self.bridge_details.setText(details)
        self.forget.setText("Exit demo" if demo else "Forget bridge")
