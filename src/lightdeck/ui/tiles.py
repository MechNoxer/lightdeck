"""Cards for lights, rooms and scenes."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QMenu, QVBoxLayout, QWidget

from .. import colors
from ..hue.models import GroupView, LightView, SceneView
from . import icons, theme
from .widgets import ColorDot, GlowCard, muted_fill, PillSlider, ToggleSwitch, icon_button, label, rgb_qcolor


def brightness_fill(rgb: colors.RGB) -> QColor:
    """A light's color, nudged so it still reads as a fill on the slider."""
    r, g, b = rgb
    if max(r, g, b) - min(r, g, b) < 0.08:  # near-white: use a warm cream instead of flat white
        return QColor("#ffe8c2")
    return rgb_qcolor(rgb)


class LightTile(GlowCard):
    powerToggled = Signal(str, bool)
    brightnessChanged = Signal(str, int)
    opened = Signal(str)

    def __init__(self, light: LightView, parent: QWidget | None = None) -> None:
        super().__init__(parent, clickable=True)
        self.light_id = light.id
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        top = QHBoxLayout()
        top.setSpacing(10)
        self.dot = ColorDot(36)
        text = QVBoxLayout()
        text.setSpacing(1)
        self.name = label("", "CardTitle")
        self.meta = label("", "CardMeta")
        text.addWidget(self.name)
        text.addWidget(self.meta)
        self.toggle = ToggleSwitch()
        self.toggle.toggled.connect(lambda on: self.powerToggled.emit(self.light_id, on))
        top.addWidget(self.dot)
        top.addLayout(text, 1)
        top.addWidget(self.toggle, 0, Qt.AlignVCenter)
        layout.addLayout(top)

        self.slider = PillSlider(height=34)
        self.slider.valueChanged.connect(lambda v: self.brightnessChanged.emit(self.light_id, v))
        layout.addWidget(self.slider)
        self.clicked.connect(lambda: self.opened.emit(self.light_id))
        self.setToolTip("Click for color and temperature")
        self.update_light(light)

    def update_light(self, light: LightView) -> None:
        self.name.setText(light.name)
        fill = brightness_fill(light.rgb)
        if not light.reachable:
            meta, warn = "Unreachable", True
        elif not light.on:
            meta, warn = "Off", False
        else:
            meta, warn = f"{round(light.brightness)}%", False
        self.meta.setText(meta)
        if self.meta.property("warn") != warn:
            self.meta.setProperty("warn", warn)
            self.meta.style().unpolish(self.meta)
            self.meta.style().polish(self.meta)
        lit = light.on and light.reachable
        self.toggle.setChecked(light.on)
        self.toggle.setEnabled(light.reachable)
        self.slider.setEnabled(light.reachable and light.has_dimming)
        self.slider.setValue(round(light.brightness))
        self.slider.setFillColor(fill if lit else muted_fill())
        self.dot.set_color(rgb_qcolor(light.rgb) if lit else None)
        self.set_glow([rgb_qcolor(light.rgb)] if lit else [])


class RoomCard(GlowCard):
    powerToggled = Signal(str, bool)
    brightnessChanged = Signal(str, int)
    opened = Signal(str)

    def __init__(self, group: GroupView, parent: QWidget | None = None) -> None:
        super().__init__(parent, clickable=True)
        self.group_id = group.id
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)
        top = QHBoxLayout()
        top.setSpacing(10)
        self.dot = ColorDot(40, "room" if group.kind == "room" else "zone")
        text = QVBoxLayout()
        text.setSpacing(1)
        self.name = label(group.name, "CardTitle")
        self.meta = label("", "CardMeta")
        text.addWidget(self.name)
        text.addWidget(self.meta)
        self.toggle = ToggleSwitch()
        self.toggle.toggled.connect(lambda on: self.powerToggled.emit(self.group_id, on))
        top.addWidget(self.dot)
        top.addLayout(text, 1)
        top.addWidget(self.toggle, 0, Qt.AlignVCenter)
        layout.addLayout(top)
        self.slider = PillSlider(height=36)
        self.slider.valueChanged.connect(lambda v: self.brightnessChanged.emit(self.group_id, v))
        layout.addWidget(self.slider)
        self.clicked.connect(lambda: self.opened.emit(self.group_id))

    def update_group(self, group: GroupView, lights: list[LightView]) -> None:
        self.name.setText(group.name)
        reachable = [l for l in lights if l.reachable]
        lit = [l for l in reachable if l.on]
        if not lights:
            meta = "No lights"
        elif not lit:
            meta = "All off"
        elif len(lit) == len(reachable):
            meta = "All on" if len(lit) > 1 else "On"
        else:
            meta = f"{len(lit)} of {len(reachable)} on"
        self.meta.setText(meta)
        self.toggle.setChecked(bool(lit))
        self.toggle.setEnabled(bool(reachable))
        self.slider.setEnabled(bool(reachable))
        if lit:
            self.slider.setValue(round(sum(l.brightness for l in lit) / len(lit)))
            glow = _distinct([rgb_qcolor(l.rgb) for l in lit])
            self.slider.setFillColor(brightness_fill(lit[0].rgb))
            self.dot.set_color(glow[0])
            self.set_glow(glow[:3])
        else:
            if reachable:
                self.slider.setValue(round(sum(l.brightness for l in reachable) / len(reachable)))
            self.slider.setFillColor(muted_fill())
            self.dot.set_color(None)
            self.set_glow([])


def _distinct(items: list[QColor]) -> list[QColor]:
    result: list[QColor] = []
    for color in items:
        if all(abs(color.red() - c.red()) + abs(color.green() - c.green()) + abs(color.blue() - c.blue()) > 40 for c in result):
            result.append(color)
    return result


class SceneTile(QWidget):
    activated = Signal(str)
    editRequested = Signal(str)
    deleteRequested = Signal(str)

    def __init__(self, scene: SceneView, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.scene_id = scene.id
        self._scene = scene
        self._hover = False
        self.setFixedHeight(86)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(lambda pos: self._menu(self.mapToGlobal(pos)))
        self.more = icon_button("more", "Scene options", 16)
        self.more.setParent(self)
        self.more.setStyleSheet("QPushButton { background: rgba(0,0,0,0.25); border-radius: 8px; }")
        self.more.setIcon(icons.icon("more", "#ffffff", 16))
        self.more.setProperty("icon_name", None)
        self.more.clicked.connect(lambda: self._menu(self.more.mapToGlobal(self.more.rect().bottomLeft())))
        self.more.hide()

    def update_scene(self, scene: SceneView) -> None:
        if scene != self._scene:
            self._scene = scene
            self.update()

    def _menu(self, pos) -> None:
        menu = QMenu(self)
        menu.addAction(icons.icon("edit", theme.current().text, 16), "Edit scene…",
                       lambda: self.editRequested.emit(self.scene_id))
        menu.addAction(icons.icon("trash", theme.current().danger, 16), "Delete scene",
                       lambda: self.deleteRequested.emit(self.scene_id))
        menu.exec(pos)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        self.more.move(self.width() - self.more.width() - 8, 8)

    def enterEvent(self, event) -> None:  # type: ignore[override]
        self._hover = True
        self.more.show()
        self.update()

    def leaveEvent(self, event) -> None:  # type: ignore[override]
        self._hover = False
        self.more.hide()
        self.update()

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.activated.emit(self.scene_id)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        p = theme.current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        path = QPainterPath()
        path.addRoundedRect(rect, theme.RADIUS, theme.RADIUS)
        stops = [rgb_qcolor(c) for c in self._scene.preview_colors] or [theme.qcolor(p.track)]
        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        if len(stops) == 1:
            gradient.setColorAt(0, stops[0])
            gradient.setColorAt(1, stops[0].darker(135))
        else:
            for index, color in enumerate(stops):
                gradient.setColorAt(index / (len(stops) - 1), color)
        painter.fillPath(path, gradient)
        # Darken the bottom for legible text
        shade = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        shade.setColorAt(0.35, QColor(0, 0, 0, 0))
        shade.setColorAt(1.0, QColor(0, 0, 0, 120 if not self._hover else 150))
        painter.fillPath(path, shade)

        if self._scene.active:
            painter.setPen(QPen(theme.qcolor(p.text), 2.5))
            painter.drawPath(path)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#ffffff"))
            painter.drawEllipse(QPointF(rect.left() + 18, rect.top() + 18), 9, 9)
            painter.drawPixmap(QPointF(rect.left() + 11, rect.top() + 11), icons.pixmap("check", "#111111", 14))

        font = QFont(self.font())
        font.setPixelSize(14)
        font.setWeight(QFont.DemiBold)
        painter.setFont(font)
        painter.setPen(QColor("#ffffff"))
        text_rect = rect.adjusted(14, 0, -14, -12)
        name = painter.fontMetrics().elidedText(self._scene.name, Qt.ElideRight, int(text_rect.width()))
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignBottom, name)


class AddSceneTile(QWidget):
    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(86)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        self.setToolTip("Save the room's current lights as a new scene")

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()

    def enterEvent(self, event) -> None:  # type: ignore[override]
        self.update()

    def leaveEvent(self, event) -> None:  # type: ignore[override]
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        p = theme.current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        hover = self.underMouse()
        painter.setPen(QPen(theme.qcolor(p.accent if hover else p.text_muted), 1.5, Qt.DashLine))
        painter.setBrush(theme.qcolor(p.surface_hover if hover else p.surface))
        painter.drawRoundedRect(rect, theme.RADIUS, theme.RADIUS)
        color = p.accent if hover else p.text_secondary
        painter.drawPixmap(QPointF(rect.center().x() - 52, rect.center().y() - 9), icons.pixmap("plus", color, 18))
        font = QFont(self.font())
        font.setWeight(QFont.DemiBold)
        painter.setFont(font)
        painter.setPen(theme.qcolor(color))
        painter.drawText(rect.adjusted(30, 0, 0, 0), Qt.AlignCenter, "New scene")
