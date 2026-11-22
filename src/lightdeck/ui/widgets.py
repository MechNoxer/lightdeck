"""Custom-painted controls: pill slider, toggle, color wheel, cards, layouts."""

from __future__ import annotations

import math
from typing import Callable, Sequence

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QConicalGradient,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QWidgetItem,
)

from .. import colors
from . import icons, theme


def rgb_qcolor(rgb: colors.RGB, alpha: float = 1.0) -> QColor:
    return QColor.fromRgbF(rgb[0], rgb[1], rgb[2], alpha)


def luminance(color: QColor) -> float:
    return 0.2126 * color.redF() + 0.7152 * color.greenF() + 0.0722 * color.blueF()


def label(text: str = "", object_name: str = "", word_wrap: bool = False) -> QLabel:
    widget = QLabel(text)
    if object_name:
        widget.setObjectName(object_name)
    widget.setWordWrap(word_wrap)
    return widget


def button(text: str, kind: str = "", icon_name: str | None = None) -> QPushButton:
    widget = QPushButton(text)
    if kind:
        widget.setObjectName(kind)
    widget.setCursor(Qt.PointingHandCursor)
    if icon_name:
        color = theme.current().accent_text if kind == "Primary" else theme.current().text
        widget.setIcon(icons.icon(icon_name, color, 16))
    return widget


def icon_button(icon_name: str, tooltip: str, size: int = 18) -> QPushButton:
    widget = QPushButton()
    widget.setObjectName("Icon")
    widget.setToolTip(tooltip)
    widget.setCursor(Qt.PointingHandCursor)
    widget.setIcon(icons.icon(icon_name, theme.current().text_secondary, size))
    widget.setIconSize(QSize(size, size))
    widget.setProperty("icon_name", icon_name)
    return widget


def refresh_icon_buttons(root: QWidget) -> None:
    """Re-tint icon buttons after a theme change."""
    for child in root.findChildren(QPushButton):
        name = child.property("icon_name")
        if name:
            child.setIcon(icons.icon(name, theme.current().text_secondary, child.iconSize().width()))


# ---------------------------------------------------------------------------
# Toggle switch
# ---------------------------------------------------------------------------

class ToggleSwitch(QWidget):
    toggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None, small: bool = False) -> None:
        super().__init__(parent)
        self._checked = False
        self._position = 0.0
        self.setFixedSize(QSize(38, 22) if small else QSize(46, 26))
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self._animation = QPropertyAnimation(self, b"position", self)
        self._animation.setDuration(160)
        self._animation.setEasingCurve(QEasingCurve.OutCubic)

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool, animate: bool = False) -> None:
        if self._checked == checked:
            return
        self._checked = checked
        target = 1.0 if checked else 0.0
        self._animation.stop()
        if animate:
            self._animation.setStartValue(self._position)
            self._animation.setEndValue(target)
            self._animation.start()
        else:
            self._position = target
            self.update()

    def _toggle(self) -> None:
        self.setChecked(not self._checked, animate=True)
        self.toggled.emit(self._checked)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton and self.isEnabled() and self.rect().contains(event.position().toPoint()):
            self._toggle()

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if event.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
            self._toggle()
        else:
            super().keyPressEvent(event)

    def _get_position(self) -> float:
        return self._position

    def _set_position(self, value: float) -> None:
        self._position = value
        self.update()

    position = Property(float, _get_position, _set_position)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        p = theme.current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        radius = rect.height() / 2
        off, on = theme.qcolor(p.track), theme.qcolor(p.accent)
        t = self._position
        track = QColor.fromRgbF(
            off.redF() + (on.redF() - off.redF()) * t,
            off.greenF() + (on.greenF() - off.greenF()) * t,
            off.blueF() + (on.blueF() - off.blueF()) * t,
        )
        if not self.isEnabled():
            painter.setOpacity(0.4)
        painter.setPen(Qt.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(rect, radius, radius)
        if self.hasFocus():
            painter.setPen(QPen(theme.qcolor(p.accent), 1.5))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect, radius, radius)
            painter.setPen(Qt.NoPen)
        knob = rect.height() - 6
        x = rect.x() + 3 + (rect.width() - knob - 6) * t
        painter.setBrush(QColor(0, 0, 0, 40))
        painter.drawEllipse(QRectF(x, rect.y() + 4, knob, knob))
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(QRectF(x, rect.y() + 3, knob, knob))


class CheckBox(QAbstractButton):
    """A rounded checkbox with a drawn checkmark (QSS can't draw one without image files)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(22, 22)
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        p = theme.current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        if self.isChecked():
            painter.setPen(Qt.NoPen)
            painter.setBrush(theme.qcolor(p.accent))
            painter.drawRoundedRect(rect, 5, 5)
            painter.drawPixmap(QPointF(rect.left() + 2, rect.top() + 2), icons.pixmap("check", p.accent_text, int(rect.width() - 4)))
        else:
            painter.setPen(QPen(theme.qcolor(p.text_muted), 1.5))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect, 5, 5)
        if self.hasFocus():
            painter.setPen(QPen(theme.qcolor(p.accent), 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 6, 6)


def muted_fill() -> QColor:
    color = theme.qcolor(theme.current().text_muted)
    color.setAlphaF(0.5)
    return color


# ---------------------------------------------------------------------------
# Pill slider
# ---------------------------------------------------------------------------

class PillSlider(QWidget):
    """A thick, rounded slider. Click anywhere to jump, drag to adjust.

    ``valueChanged`` fires continuously during interaction (user input only);
    ``released`` fires once the interaction ends. Programmatic ``setValue``
    calls are ignored while the user is dragging so live updates from the
    bridge can't fight the pointer.
    """

    valueChanged = Signal(int)
    released = Signal(int)

    def __init__(
        self,
        minimum: int = 1,
        maximum: int = 100,
        value: int = 50,
        *,
        height: int = 40,
        icon_name: str | None = "sun",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._min, self._max = minimum, maximum
        self._value = value
        self._dragging = False
        self._fill = QColor("#f5a524")
        self._gradient: list[tuple[float, QColor]] | None = None
        self._icon_name = icon_name
        self._formatter: Callable[[int], str] = lambda v: f"{v}%"
        self._show_text = True
        self._step = max(1, (maximum - minimum) // 50)
        self.setFixedHeight(height)
        self.setMinimumWidth(80)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self._release_timer = QTimer(self)
        self._release_timer.setSingleShot(True)
        self._release_timer.setInterval(350)
        self._release_timer.timeout.connect(lambda: self.released.emit(self._value))

    # configuration
    def setRange(self, minimum: int, maximum: int) -> None:
        self._min, self._max = minimum, max(minimum + 1, maximum)
        self._step = max(1, (self._max - self._min) // 50)
        self._value = max(self._min, min(self._max, self._value))
        self.update()

    def setFillColor(self, color: QColor) -> None:
        self._gradient = None
        if color != self._fill:
            self._fill = color
            self.update()

    def setGradient(self, stops: Sequence[tuple[float, QColor]]) -> None:
        self._gradient = list(stops)
        self.update()

    def setFormatter(self, formatter: Callable[[int], str]) -> None:
        self._formatter = formatter
        self.update()

    def setShowText(self, show: bool) -> None:
        self._show_text = show
        self.update()

    def setStep(self, step: int) -> None:
        self._step = max(1, step)

    # value
    def value(self) -> int:
        return self._value

    def isDragging(self) -> bool:
        return self._dragging

    def setValue(self, value: int) -> None:
        if self._dragging:
            return
        value = max(self._min, min(self._max, int(round(value))))
        if value != self._value:
            self._value = value
            self.update()

    def _set_from_user(self, value: int) -> None:
        value = max(self._min, min(self._max, int(round(value))))
        if value != self._value:
            self._value = value
            self.update()
            self.valueChanged.emit(value)

    def _value_at(self, x: float) -> int:
        inset = self.height() / 2
        span = max(1.0, self.width() - inset * 2)
        t = max(0.0, min(1.0, (x - inset) / span))
        return round(self._min + t * (self._max - self._min))

    def _ratio(self) -> float:
        return (self._value - self._min) / max(1, self._max - self._min)

    # input
    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() != Qt.LeftButton or not self.isEnabled():
            return
        self._dragging = True
        self._set_from_user(self._value_at(event.position().x()))

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._dragging:
            self._set_from_user(self._value_at(event.position().x()))

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if self._dragging:
            self._dragging = False
            self.released.emit(self._value)

    def wheelEvent(self, event) -> None:  # type: ignore[override]
        if not self.isEnabled():
            return
        delta = event.angleDelta().y() or event.angleDelta().x()
        if delta:
            self._set_from_user(self._value + (self._step if delta > 0 else -self._step))
            self._release_timer.start()
        event.accept()

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        big = max(self._step * 5, (self._max - self._min) // 10)
        moves = {
            Qt.Key_Left: -self._step, Qt.Key_Down: -self._step,
            Qt.Key_Right: self._step, Qt.Key_Up: self._step,
            Qt.Key_PageDown: -big, Qt.Key_PageUp: big,
        }
        if event.key() in moves:
            self._set_from_user(self._value + moves[event.key()])
        elif event.key() == Qt.Key_Home:
            self._set_from_user(self._min)
        elif event.key() == Qt.Key_End:
            self._set_from_user(self._max)
        else:
            super().keyPressEvent(event)
            return
        self._release_timer.start()

    # painting
    def paintEvent(self, event) -> None:  # type: ignore[override]
        p = theme.current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if not self.isEnabled():
            painter.setOpacity(0.45)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = rect.height() / 2
        track = QPainterPath()
        track.addRoundedRect(rect, radius, radius)

        if self._gradient:
            gradient = QLinearGradient(rect.topLeft(), rect.topRight())
            for position, color in self._gradient:
                gradient.setColorAt(position, color)
            painter.fillPath(track, QBrush(gradient))
            painter.setPen(QPen(theme.qcolor(p.border), 1))
            painter.drawPath(track)
            cx = rect.left() + radius + (rect.width() - 2 * radius) * self._ratio()
            knob = QRectF(cx - radius + 4, rect.top() + 4, rect.height() - 8, rect.height() - 8)
            painter.setPen(QPen(QColor(0, 0, 0, 60), 4))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(knob)
            painter.setPen(QPen(QColor("#ffffff"), 3))
            painter.drawEllipse(knob)
        else:
            painter.fillPath(track, theme.qcolor(p.track))
            fill_w = rect.height() + (rect.width() - rect.height()) * self._ratio()
            fill = QPainterPath()
            fill.addRoundedRect(QRectF(rect.left(), rect.top(), fill_w, rect.height()), radius, radius)
            painter.fillPath(fill, self._fill)
            # A small grip line at the end of the fill
            grip_x = rect.left() + fill_w - radius * 0.62
            text_zone = rect.right() - radius * 0.9 - rect.height() * 1.5
            if not (self._show_text and grip_x > text_zone):
                grip_color = QColor(0, 0, 0, 70) if luminance(self._fill) > 0.55 else QColor(255, 255, 255, 150)
                painter.setPen(QPen(grip_color, 2.5, Qt.SolidLine, Qt.RoundCap))
                painter.drawLine(QPointF(grip_x, rect.center().y() - radius * 0.36),
                                 QPointF(grip_x, rect.center().y() + radius * 0.36))

            if self._icon_name:
                size = int(rect.height() * 0.42)
                icon_color = "#1a1a1a" if luminance(self._fill) > 0.55 else "#ffffff"
                pix = icons.pixmap(self._icon_name, icon_color, size)
                painter.drawPixmap(QPointF(rect.left() + (rect.height() - size) / 2, rect.center().y() - size / 2), pix)

        if self._show_text:
            font = QFont(self.font())
            font.setPixelSize(max(11, int(rect.height() * 0.32)))
            font.setWeight(QFont.DemiBold)
            painter.setFont(font)
            text = self._formatter(self._value)
            text_rect = rect.adjusted(0, 0, -radius * 0.9, 0)
            if self._gradient:
                painter.setPen(QColor(20, 20, 20, 200))
            else:
                fill_right = rect.left() + rect.height() + (rect.width() - rect.height()) * self._ratio()
                covered = fill_right > text_rect.right() - 10
                dark_text = luminance(self._fill) > 0.55 if covered else not p.dark
                painter.setPen(QColor("#1a1a1a") if dark_text else QColor("#ffffff") if covered else theme.qcolor(p.text_secondary))
            painter.drawText(text_rect, Qt.AlignRight | Qt.AlignVCenter, text)

        if self.hasFocus():
            painter.setOpacity(1.0)
            painter.setPen(QPen(theme.qcolor(p.accent), 1.5))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(track)


def temperature_stops(mirek_min: int, mirek_max: int, steps: int = 8) -> list[tuple[float, QColor]]:
    """Gradient for a Kelvin slider that runs warm (left) to cool (right)."""
    k_low, k_high = colors.mirek_to_kelvin(mirek_max), colors.mirek_to_kelvin(mirek_min)
    return [
        (i / steps, rgb_qcolor(colors.kelvin_to_rgb(k_low + (k_high - k_low) * i / steps)))
        for i in range(steps + 1)
    ]


class TemperatureSlider(PillSlider):
    """Kelvin slider: warm on the left, cool on the right. Emits mirek."""

    mirekChanged = Signal(int)
    mirekReleased = Signal(int)

    def __init__(self, mirek_min: int = 153, mirek_max: int = 500, *, height: int = 40, parent: QWidget | None = None) -> None:
        super().__init__(height=height, icon_name=None, parent=parent)
        self.setStep(50)
        self.setFormatter(lambda k: f"{round(k / 50) * 50} K")
        self.set_range_mirek(mirek_min, mirek_max)
        self.valueChanged.connect(lambda k: self.mirekChanged.emit(self._to_mirek(k)))
        self.released.connect(lambda k: self.mirekReleased.emit(self._to_mirek(k)))

    def set_range_mirek(self, mirek_min: int, mirek_max: int) -> None:
        self._mirek_min, self._mirek_max = mirek_min, mirek_max
        self.setRange(colors.mirek_to_kelvin(mirek_max), colors.mirek_to_kelvin(mirek_min))
        self.setGradient(temperature_stops(mirek_min, mirek_max))

    def _to_mirek(self, kelvin: int) -> int:
        return max(self._mirek_min, min(self._mirek_max, colors.kelvin_to_mirek(kelvin)))

    def set_mirek(self, mirek: int | None) -> None:
        if mirek:
            self.setValue(colors.mirek_to_kelvin(mirek))


# ---------------------------------------------------------------------------
# Color wheel
# ---------------------------------------------------------------------------

class ColorWheel(QWidget):
    """Hue around the circle, saturation from center (white) to edge."""

    colorChanged = Signal(float, float)  # hue degrees, saturation 0..1
    released = Signal(float, float)

    def __init__(self, diameter: int = 240, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._hue, self._sat = 30.0, 0.6
        self._dragging = False
        self.setFixedSize(diameter, diameter)
        self.setCursor(Qt.CrossCursor)

    def isDragging(self) -> bool:
        return self._dragging

    def set_hs(self, hue: float, saturation: float) -> None:
        if self._dragging:
            return
        self._hue, self._sat = hue % 360, max(0.0, min(1.0, saturation))
        self.update()

    def color(self) -> QColor:
        return QColor.fromHsvF(self._hue / 360, self._sat, 1.0)

    def _geometry(self) -> tuple[QPointF, float]:
        return QPointF(self.width() / 2, self.height() / 2), min(self.width(), self.height()) / 2 - 12

    def _update_from(self, pos: QPointF) -> None:
        center, radius = self._geometry()
        dx, dy = pos.x() - center.x(), center.y() - pos.y()
        self._hue = (math.degrees(math.atan2(dy, dx)) + 360) % 360
        self._sat = min(1.0, math.hypot(dx, dy) / radius)
        self.update()
        self.colorChanged.emit(self._hue, self._sat)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton and self.isEnabled():
            self._dragging = True
            self._update_from(event.position())

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._dragging:
            self._update_from(event.position())

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if self._dragging:
            self._dragging = False
            self.released.emit(self._hue, self._sat)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if not self.isEnabled():
            painter.setOpacity(0.4)
        center, radius = self._geometry()
        disk = QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2)

        hue_gradient = QConicalGradient(center, 0)
        for step in range(13):
            hue_gradient.setColorAt(step / 12, QColor.fromHsvF((step % 12) / 12, 1.0, 1.0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(hue_gradient)
        painter.drawEllipse(disk)

        white = QRadialGradient(center, radius)
        white.setColorAt(0.0, QColor(255, 255, 255, 255))
        white.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setBrush(white)
        painter.drawEllipse(disk)

        angle = math.radians(self._hue)
        knob = QPointF(center.x() + math.cos(angle) * radius * self._sat,
                       center.y() - math.sin(angle) * radius * self._sat)
        painter.setPen(QPen(QColor(0, 0, 0, 70), 5))
        painter.setBrush(self.color())
        painter.drawEllipse(knob, 12, 12)
        painter.setPen(QPen(QColor("#ffffff"), 3))
        painter.drawEllipse(knob, 12, 12)


# ---------------------------------------------------------------------------
# Segmented control
# ---------------------------------------------------------------------------

class Segmented(QFrame):
    changed = Signal(int)

    def __init__(self, labels: Sequence[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SegmentedBar")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for index, text in enumerate(labels):
            item = QPushButton(text)
            item.setObjectName("Segment")
            item.setCheckable(True)
            item.setCursor(Qt.PointingHandCursor)
            self._group.addButton(item, index)
            layout.addWidget(item)
        self._group.idClicked.connect(self.changed.emit)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)

    def set_index(self, index: int) -> None:
        item = self._group.button(index)
        if item:
            item.setChecked(True)

    def index(self) -> int:
        return self._group.checkedId()


# ---------------------------------------------------------------------------
# Cards
# ---------------------------------------------------------------------------

class GlowCard(QFrame):
    """A rounded surface that tints itself with the colors of its lights."""

    clicked = Signal()

    def __init__(self, parent: QWidget | None = None, clickable: bool = False) -> None:
        super().__init__(parent)
        self._glow: list[QColor] = []
        self._hover = False
        self._clickable = clickable
        self._press_pos: QPoint | None = None
        if clickable:
            self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)

    def set_glow(self, glow: Sequence[QColor]) -> None:
        glow = list(glow)
        if [c.rgba() for c in glow] != [c.rgba() for c in self._glow]:
            self._glow = glow
            self.update()

    def enterEvent(self, event) -> None:  # type: ignore[override]
        self._hover = True
        self.update()

    def leaveEvent(self, event) -> None:  # type: ignore[override]
        self._hover = False
        self.update()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if self._clickable and event.button() == Qt.LeftButton:
            self._press_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if self._clickable and self._press_pos is not None and event.button() == Qt.LeftButton:
            if self.rect().contains(event.position().toPoint()):
                self.clicked.emit()
        self._press_pos = None
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        p = theme.current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, theme.RADIUS, theme.RADIUS)
        base = theme.qcolor(p.surface_hover if (self._hover and self._clickable) else p.surface)
        painter.fillPath(path, base)
        if self._glow:
            gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
            alpha = 0.22 if p.dark else 0.16
            for index, color in enumerate(self._glow):
                tinted = QColor(color)
                tinted.setAlphaF(alpha)
                gradient.setColorAt(index / max(1, len(self._glow) - 1) if len(self._glow) > 1 else 0, tinted)
            if len(self._glow) == 1:
                fade = QColor(self._glow[0])
                fade.setAlphaF(alpha * 0.25)
                gradient.setColorAt(1, fade)
            painter.fillPath(path, gradient)
        painter.setPen(QPen(theme.qcolor(p.border), 1))
        painter.drawPath(path)


class ColorDot(QWidget):
    """A round swatch, optionally clickable, showing a light or scene color."""

    clicked = Signal()

    def __init__(self, size: int = 36, icon_name: str | None = "bulb", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color: QColor | None = None
        self._icon_name = icon_name
        self.setFixedSize(size, size)

    def set_color(self, color: QColor | None) -> None:
        if color != self._color:
            self._color = color
            self.update()

    def setClickable(self, clickable: bool) -> None:
        self.setCursor(Qt.PointingHandCursor if clickable else Qt.ArrowCursor)
        self._clickable = clickable

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if getattr(self, "_clickable", False) and event.button() == Qt.LeftButton:
            self.clicked.emit()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        p = theme.current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        fill = self._color or theme.qcolor(p.track)
        painter.setPen(QPen(theme.qcolor(p.border), 1))
        painter.setBrush(fill)
        painter.drawEllipse(rect)
        if self._icon_name:
            size = int(rect.width() * 0.5)
            dark = self._color is not None and luminance(fill) > 0.55
            color = "#1a1a1a" if dark else ("#ffffff" if self._color is not None else p.text_muted)
            painter.drawPixmap(
                QPointF(rect.center().x() - size / 2, rect.center().y() - size / 2),
                icons.pixmap(self._icon_name, color, size),
            )


# ---------------------------------------------------------------------------
# Responsive grid layout
# ---------------------------------------------------------------------------

class GridFlowLayout(QLayout):
    """Equal-width columns; the column count follows the available width."""

    def __init__(self, min_column_width: int = 240, spacing: int = 12, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._items: list = []
        self._min_w = min_column_width
        self._spacing = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item) -> None:  # type: ignore[override]
        self._items.append(item)

    def addWidget(self, widget: QWidget) -> None:  # type: ignore[override]
        self.addChildWidget(widget)
        self.addItem(QWidgetItem(widget))
        self.invalidate()

    def count(self) -> int:  # type: ignore[override]
        return len(self._items)

    def itemAt(self, index: int):  # type: ignore[override]
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int):  # type: ignore[override]
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):  # type: ignore[override]
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:  # type: ignore[override]
        return True

    def heightForWidth(self, width: int) -> int:  # type: ignore[override]
        return self._do_layout(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect: QRect) -> None:  # type: ignore[override]
        super().setGeometry(rect)
        self._do_layout(rect, apply=True)

    def sizeHint(self) -> QSize:  # type: ignore[override]
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # type: ignore[override]
        height = max((item.sizeHint().height() for item in self._items), default=0)
        return QSize(self._min_w, height)

    def _do_layout(self, rect: QRect, apply: bool) -> int:
        items = [item for item in self._items if not item.isEmpty()]
        if not items:
            return 0
        width = max(1, rect.width())
        columns = max(1, (width + self._spacing) // (self._min_w + self._spacing))
        cell_w = (width - self._spacing * (columns - 1)) / columns
        y = rect.y()
        for row_start in range(0, len(items), columns):
            row = items[row_start:row_start + columns]
            row_h = max(
                item.heightForWidth(int(cell_w)) if item.hasHeightForWidth() else item.sizeHint().height()
                for item in row
            )
            if apply:
                for col, item in enumerate(row):
                    x = rect.x() + round(col * (cell_w + self._spacing))
                    item.setGeometry(QRect(x, y, round(cell_w), row_h))
            y += row_h + self._spacing
        return y - self._spacing - rect.y()


class ResponsiveGrid(QWidget):
    def __init__(self, min_column_width: int = 240, spacing: int = 12, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = GridFlowLayout(min_column_width, spacing, self)
        sp = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        sp.setHeightForWidth(True)
        self.setSizePolicy(sp)

    def set_widgets(self, widgets: Sequence[QWidget]) -> None:
        """Replace the grid's contents. Widgets no longer present are deleted."""
        keep = set(map(id, widgets))
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None and id(widget) not in keep:
                widget.deleteLater()
        for widget in widgets:
            self._layout.addWidget(widget)
            widget.show()
        self._layout.invalidate()
        self.updateGeometry()

    def hasHeightForWidth(self) -> bool:  # type: ignore[override]
        return True

    def heightForWidth(self, width: int) -> int:  # type: ignore[override]
        return self._layout.heightForWidth(width)


# ---------------------------------------------------------------------------
# Toasts
# ---------------------------------------------------------------------------

class ToastHost(QWidget):
    """Transient notifications stacked at the bottom of the parent widget."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 24)
        self._layout.setSpacing(8)
        self._layout.addStretch(1)
        parent.installEventFilter(self)
        self._fit()

    def eventFilter(self, obj, event) -> bool:  # type: ignore[override]
        if obj is self.parent() and event.type() == event.Type.Resize:
            self._fit()
        return False

    def _fit(self) -> None:
        self.setGeometry(self.parentWidget().rect())
        self.raise_()

    def show_message(self, text: str, kind: str = "info", timeout_ms: int = 3800) -> None:
        p = theme.current()
        # Drop duplicates of a message that's already showing
        for index in range(self._layout.count()):
            existing = self._layout.itemAt(index).widget()
            if isinstance(existing, QLabel) and existing.text() == text:
                return
        accent = p.danger if kind == "error" else p.success if kind == "success" else p.text_secondary
        toast = QLabel(text)
        toast.setStyleSheet(
            f"background: {p.surface_alt}; color: {p.text}; border: 1px solid {p.border};"
            f"border-left: 3px solid {accent}; border-radius: 10px; padding: 10px 14px; font-weight: 500;"
        )
        effect = QGraphicsOpacityEffect(toast)
        effect.setOpacity(0.0)
        toast.setGraphicsEffect(effect)
        self._layout.addWidget(toast, 0, Qt.AlignHCenter)
        self._fit()
        self.show()

        fade_in = QPropertyAnimation(effect, b"opacity", toast)
        fade_in.setDuration(180)
        fade_in.setEndValue(1.0)
        fade_in.start()

        def dismiss() -> None:
            fade_out = QPropertyAnimation(effect, b"opacity", toast)
            fade_out.setDuration(250)
            fade_out.setEndValue(0.0)
            fade_out.finished.connect(toast.deleteLater)
            fade_out.start()

        QTimer.singleShot(timeout_ms, toast, dismiss)


class Spinner(QWidget):
    def __init__(self, size: int = 18, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        self._timer.start(16)
        self.show()

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    def _tick(self) -> None:
        self._angle = (self._angle + 8) % 360
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        painter.setPen(QPen(theme.qcolor(theme.current().track), 2.5))
        painter.drawEllipse(rect)
        painter.setPen(QPen(theme.qcolor(theme.current().accent), 2.5, Qt.SolidLine, Qt.RoundCap))
        painter.drawArc(rect, -self._angle * 16, 100 * 16)
