"""Dialog for creating and editing scenes."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import colors
from ..hue.controller import HueController
from ..hue.models import GroupView, LightView, SceneView
from .color_controls import ColorControls
from .tiles import brightness_fill
from .widgets import CheckBox, ColorDot, muted_fill, PillSlider, ToggleSwitch, button, label, rgb_qcolor

Raw = dict[str, Any]


class _ColorPopover(QWidget):
    def __init__(self, row: "SceneLightRow") -> None:
        super().__init__(row, Qt.Popup)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)
        frame = QFrame(self)
        frame.setObjectName("Panel")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(frame)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 16, 18, 18)
        light = row.light
        controls = ColorControls(wheel_size=220)
        controls.configure(has_color=light.has_color, has_ct=light.has_ct, gamut=light.gamut,
                           mirek_min=light.mirek_min, mirek_max=light.mirek_max)
        controls.set_state(row.mode, row.xy, row.mirek)
        controls.xyChanged.connect(lambda x, y: row.set_color(xy=(x, y)))
        controls.mirekChanged.connect(lambda m: row.set_color(mirek=m))
        layout.addWidget(controls)
        self.setFixedWidth(300)


class SceneLightRow(QFrame):
    changed = Signal()

    def __init__(self, light: LightView, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Panel")
        self.light = light
        self.on = light.on
        self.brightness = light.brightness
        self.mode = light.mode
        self.xy = light.xy
        self.mirek = light.mirek

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 14, 10)
        layout.setSpacing(12)
        self.include = CheckBox()
        self.include.setChecked(True)
        self.include.setToolTip("Include this light in the scene")
        self.include.toggled.connect(self._on_include)
        self.dot = ColorDot(34)
        can_color = light.has_color or light.has_ct
        self.dot.setClickable(can_color)
        self.dot.setToolTip("Change color" if can_color else "")
        self.dot.clicked.connect(self._open_color)
        self.name = label(light.name, "CardTitle")
        self.name.setMinimumWidth(110)
        self.toggle = ToggleSwitch(small=True)
        self.toggle.toggled.connect(self._on_power)
        self.slider = PillSlider(height=30)
        self.slider.setMinimumWidth(140)
        self.slider.valueChanged.connect(self._on_brightness)
        self.slider.setVisible(light.has_dimming)

        layout.addWidget(self.include)
        layout.addWidget(self.dot)
        layout.addWidget(self.name)
        layout.addWidget(self.toggle)
        layout.addWidget(self.slider, 1)
        self._render()

    # -- state -------------------------------------------------------------

    def load_action(self, action: Raw | None) -> None:
        if action is None:
            self.include.setChecked(False)
            return
        self.include.setChecked(True)
        self.on = action.get("on", {}).get("on", True)
        if "dimming" in action:
            self.brightness = action["dimming"].get("brightness", self.brightness)
        if action.get("color", {}).get("xy"):
            xy = action["color"]["xy"]
            self.xy, self.mode = (xy["x"], xy["y"]), "color"
        if action.get("color_temperature", {}).get("mirek"):
            self.mirek, self.mode = action["color_temperature"]["mirek"], "ct"
        self._render()

    def load_light(self, light: LightView) -> None:
        self.light = light
        self.on, self.brightness, self.mode = light.on, light.brightness, light.mode
        self.xy, self.mirek = light.xy, light.mirek
        self._render()

    def included(self) -> bool:
        return self.include.isChecked()

    def state(self) -> dict[str, Any]:
        if not self.on:
            return {"on": False}
        state: dict[str, Any] = {"on": True}
        if self.light.has_dimming:
            state["brightness"] = self.brightness
        if self.mode == "color" and self.xy and self.light.has_color:
            state["xy"] = self.xy
        elif self.mode == "ct" and self.mirek and self.light.has_ct:
            state["mirek"] = self.mirek
        return state

    def action(self) -> Raw:
        return {
            "target": {"rid": self.light.id, "rtype": "light"},
            "action": HueController.build_state(**self.state()),
        }

    def set_color(self, *, xy: colors.XY | None = None, mirek: int | None = None) -> None:
        if xy is not None:
            self.xy, self.mode = xy, "color"
        if mirek is not None:
            self.mirek, self.mode = mirek, "ct"
        self.on = True
        self._render()
        self.changed.emit()

    def _color(self) -> colors.RGB:
        if self.mode == "color" and self.xy:
            return colors.xy_to_rgb(*self.xy)
        if self.mode == "ct" and self.mirek:
            return colors.mirek_to_rgb(self.mirek)
        return colors.kelvin_to_rgb(2700)

    def _render(self) -> None:
        enabled = self.include.isChecked()
        for widget in (self.dot, self.toggle, self.slider, self.name):
            widget.setEnabled(enabled)
        self.toggle.setChecked(self.on)
        self.slider.setValue(round(self.brightness))
        self.slider.setFillColor(brightness_fill(self._color()) if self.on else muted_fill())
        self.dot.set_color(rgb_qcolor(self._color()) if self.on and enabled else None)

    # -- handlers ----------------------------------------------------------

    def _on_include(self, _checked: bool) -> None:
        self._render()
        self.changed.emit()

    def _on_power(self, on: bool) -> None:
        self.on = on
        self._render()
        self.changed.emit()

    def _on_brightness(self, value: int) -> None:
        self.brightness = value
        if not self.on:
            self.on = True
            self.toggle.setChecked(True, animate=True)
        self._render()
        self.changed.emit()

    def _open_color(self) -> None:
        if not self.include.isChecked():
            return
        popover = _ColorPopover(self)
        popover.adjustSize()
        anchor = self.dot.mapToGlobal(QPoint(0, self.dot.height() + 6))
        screen = self.screen().availableGeometry()
        x = min(anchor.x(), screen.right() - popover.width() - 8)
        y = anchor.y() if anchor.y() + popover.height() < screen.bottom() else self.dot.mapToGlobal(QPoint(0, 0)).y() - popover.height() - 6
        popover.move(x, max(screen.top(), y))
        popover.show()


class SceneEditor(QDialog):
    def __init__(self, controller: HueController, group: GroupView, scene: SceneView | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.group = group
        self.scene = scene
        self._lights = controller.store.group_lights(group)
        self._snapshot = list(self._lights)
        self._previewed = False

        self.setWindowTitle("Edit scene" if scene else "New scene")
        self.setModal(True)
        self.resize(620, 600)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 22)
        layout.setSpacing(12)
        layout.addWidget(label("Edit scene" if scene else "New scene", "PanelTitle"))
        layout.addWidget(label(
            f"Set up each light in {group.name}, then save. "
            + ("Lights start from the scene's saved state." if scene else "Lights start from how they are right now."),
            "Muted", True))

        layout.addSpacing(4)
        layout.addWidget(label("Name", "FieldLabel"))
        self.name = QLineEdit(scene.name if scene else "")
        self.name.setPlaceholderText("e.g. Movie night")
        self.name.setMaxLength(32)
        self.name.textChanged.connect(self._validate)
        layout.addWidget(self.name)

        tools = QHBoxLayout()
        tools.setContentsMargins(0, 8, 0, 0)
        tools.addWidget(label("Lights", "SectionTitle"))
        tools.addStretch(1)
        self.preview = ToggleSwitch(small=True)
        self.preview.toggled.connect(self._on_preview)
        tools.addWidget(label("Preview on lights", "Muted"))
        tools.addWidget(self.preview)
        copy = button("Use current state", "Ghost")
        copy.setToolTip("Reset every light to what it's doing right now")
        copy.clicked.connect(self._copy_current)
        tools.addWidget(copy)
        layout.addLayout(tools)

        rows_host = QWidget()
        rows_layout = QVBoxLayout(rows_host)
        rows_layout.setContentsMargins(0, 0, 6, 0)
        rows_layout.setSpacing(8)
        self.rows: list[SceneLightRow] = []
        actions = {a["target"]["rid"]: a.get("action", {}) for a in (scene.actions if scene else ())}
        for light in self._lights:
            row = SceneLightRow(light)
            if scene:
                row.load_action(actions.get(light.id))
            row.changed.connect(lambda r=row: self._on_row_changed(r))
            rows_layout.addWidget(row)
            self.rows.append(row)
        if not self._lights:
            rows_layout.addWidget(label("This room has no lights.", "Muted"))
        rows_layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(rows_host)
        layout.addWidget(scroll, 1)

        self.error = label("", "CardMeta", True)
        self.error.setProperty("warn", True)
        self.error.hide()
        layout.addWidget(self.error)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 6, 0, 0)
        if scene:
            delete = button("Delete", "Danger", "trash")
            delete.clicked.connect(self._delete)
            footer.addWidget(delete)
        footer.addStretch(1)
        cancel = button("Cancel", "Ghost")
        cancel.clicked.connect(self.reject)
        self.save = button("Save scene", "Primary")
        self.save.setDefault(True)
        self.save.clicked.connect(self._save)
        footer.addWidget(cancel)
        footer.addWidget(self.save)
        layout.addLayout(footer)
        self._validate()

    def _validate(self) -> None:
        self.save.setEnabled(bool(self.name.text().strip()) and any(r.included() for r in self.rows))

    def _show_error(self, message: str) -> None:
        self.error.setText(message)
        self.error.show()
        self.save.setEnabled(True)

    def _apply_row(self, row: SceneLightRow) -> None:
        if row.included() and row.light.reachable:
            self.controller.set_light(row.light.id, **row.state())

    def _on_row_changed(self, row: SceneLightRow) -> None:
        self._validate()
        if self.preview.isChecked():
            self._apply_row(row)

    def _on_preview(self, on: bool) -> None:
        if on:
            self._previewed = True
            for row in self.rows:
                self._apply_row(row)

    def _copy_current(self) -> None:
        for row in self.rows:
            current = self.controller.store.light(row.light.id)
            if current:
                row.include.setChecked(True)
                row.load_light(current)
        self._validate()

    def _restore(self) -> None:
        if not self._previewed:
            return
        for light in self._snapshot:
            if not light.reachable:
                continue
            if not light.on:
                self.controller.set_light(light.id, on=False)
                continue
            state: dict[str, Any] = {"on": True, "brightness": light.brightness}
            if light.mode == "color" and light.xy:
                state["xy"] = light.xy
            elif light.mode == "ct" and light.mirek:
                state["mirek"] = light.mirek
            self.controller.set_light(light.id, **state)

    def reject(self) -> None:  # type: ignore[override]
        self._restore()
        super().reject()

    def _save(self) -> None:
        name = self.name.text().strip()
        actions = [row.action() for row in self.rows if row.included()]
        if not name or not actions:
            return
        self.save.setEnabled(False)
        self.error.hide()
        self.controller.save_scene(
            self.scene.id if self.scene else None, name, self.group, actions,
            on_done=self.accept, on_error=lambda msg: self._show_error(f"Couldn't save: {msg}"),
        )

    def _delete(self) -> None:
        answer = QMessageBox.question(
            self, "Delete scene", f"Delete “{self.scene.name}”? This removes it from the bridge.",
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel,
        )
        if answer == QMessageBox.Yes:
            self._restore()
            self.controller.delete_scene(self.scene.id, on_done=self.accept)
