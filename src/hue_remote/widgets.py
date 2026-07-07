"""Reusable UI building blocks: toggle switch, inline color wheel, and light card."""

from __future__ import annotations

import math

from PySide6.QtCore import Property, QEasingCurve, QPointF, QPropertyAnimation, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QConicalGradient, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .hue_api import HueBridgeClient, Light
from .theme import PRESET_COLORS, Color, Spacing, apply_elevation
from .icons import icon


def icon_label(name: str, color: str = Color.TEXT_SECONDARY, size: int = 16) -> QLabel:
    label = QLabel()
    label.setPixmap(icon(name, color, size).pixmap(size, size))
    label.setFixedSize(size, size)
    return label


def _blend(a: QColor, b: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor(
        round(a.red() + (b.red() - a.red()) * t),
        round(a.green() + (b.green() - a.green()) * t),
        round(a.blue() + (b.blue() - a.blue()) * t),
    )


class ToggleSwitch(QWidget):
    toggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._checked = False
        self._position = 0.0
        self.setFixedSize(46, 26)
        self.setCursor(Qt.PointingHandCursor)
        self._animation = QPropertyAnimation(self, b"position", self)
        self._animation.setDuration(140)
        self._animation.setEasingCurve(QEasingCurve.OutCubic)

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool, animate: bool = True) -> None:
        if self._checked == checked:
            return
        self._checked = checked
        target = 1.0 if checked else 0.0
        if animate:
            self._animation.stop()
            self._animation.setStartValue(self._position)
            self._animation.setEndValue(target)
            self._animation.start()
        else:
            self._position = target
            self.update()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton and self.isEnabled():
            checked = not self._checked
            self.setChecked(checked)
            self.toggled.emit(checked)

    def _get_position(self) -> float:
        return self._position

    def _set_position(self, value: float) -> None:
        self._position = value
        self.update()

    position = Property(float, _get_position, _set_position)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect().adjusted(1, 1, -1, -1))
        radius = rect.height() / 2

        off_color = QColor(255, 255, 255, 35)
        on_color = QColor(Color.ACCENT)
        if not self.isEnabled():
            on_color = QColor(120, 108, 90)
        background = _blend(off_color, on_color, self._position)

        painter.setPen(Qt.NoPen)
        painter.setBrush(background)
        painter.drawRoundedRect(rect, radius, radius)

        knob_diameter = rect.height() - 6
        travel = rect.width() - knob_diameter - 6
        knob_x = rect.x() + 3 + travel * self._position
        knob_rect = QRectF(knob_x, rect.y() + 3, knob_diameter, knob_diameter)
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(knob_rect)


class ColorWheelWidget(QWidget):
    colorChanged = Signal(QColor)
    colorCommitted = Signal(QColor)

    def __init__(self, parent: QWidget | None = None, size: int = 240) -> None:
        super().__init__(parent)
        self._hue = 32
        self._dragging = False
        self.setMinimumSize(size, size)
        self.setMaximumSize(size, size)

    def selected_color(self) -> QColor:
        return QColor.fromHsv(self._hue, 255, 255)

    def set_selected_color(self, color: QColor) -> None:
        hsv = color.toHsv()
        if hsv.hue() >= 0:
            self._hue = hsv.hue()
            self.colorChanged.emit(self.selected_color())
            self.update()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if not self.isEnabled():
            return
        self._dragging = True
        self.update_from_position(event.position())

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._dragging and event.buttons() & Qt.LeftButton:
            self.update_from_position(event.position())

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if self._dragging:
            self._dragging = False
            self.colorCommitted.emit(self.selected_color())

    def update_from_position(self, position: QPointF) -> None:
        center = QPointF(self.width() / 2, self.height() / 2)
        dx = position.x() - center.x()
        dy = position.y() - center.y()
        angle = (math.degrees(math.atan2(-dy, dx)) + 360) % 360
        self._hue = round(angle)
        self.colorChanged.emit(self.selected_color())
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        size = min(self.width(), self.height()) - 16
        outer_rect = QRectF((self.width() - size) / 2, (self.height() - size) / 2, size, size)

        gradient = QConicalGradient(outer_rect.center(), -90)
        for step in range(0, 361, 30):
            gradient.setColorAt(step / 360, QColor.fromHsv(step % 360, 255, 255))

        pen = QPen()
        pen.setWidth(22)
        pen.setBrush(gradient)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(outer_rect)

        inner_size = size - 70
        inner_rect = QRectF(
            (self.width() - inner_size) / 2,
            (self.height() - inner_size) / 2,
            inner_size,
            inner_size,
        )
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(28, 28, 28))
        painter.drawEllipse(inner_rect)
        painter.setBrush(self.selected_color())
        painter.drawEllipse(inner_rect.adjusted(18, 18, -18, -18))

        radius = size / 2 - 11
        angle_rad = math.radians(self._hue)
        center = outer_rect.center()
        handle_x = center.x() + math.cos(angle_rad) * radius
        handle_y = center.y() - math.sin(angle_rad) * radius
        painter.setBrush(QColor("#ffffff"))
        painter.setPen(QPen(QColor("#101010"), 2))
        painter.drawEllipse(QPointF(handle_x, handle_y), 9, 9)


def _preset_swatch_button(hex_color: str, name: str, size: int = 26) -> QPushButton:
    button = QPushButton()
    button.setObjectName("PresetSwatch")
    button.setFixedSize(size, size)
    button.setToolTip(name)
    button.setCursor(Qt.PointingHandCursor)
    button.setStyleSheet(
        f"QPushButton#PresetSwatch {{ background: {hex_color}; border-radius: {size // 2}px; }}"
    )
    return button


class LightCard(QFrame):
    powerToggled = Signal(str, bool)
    brightnessChanged = Signal(str, int)
    temperatureChanged = Signal(str, int)
    colorPicked = Signal(str, QColor)

    COLOR_MODE_INDEX = 0
    WHITE_MODE_INDEX = 1

    def __init__(self, light: Light, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.light_id = light.light_id
        self.setProperty("card", True)
        self.setMinimumHeight(220)
        apply_elevation(self, blur=22, y_offset=6, alpha=90)

        self.temperature_slider: QSlider | None = None
        self.temperature_value: QLabel | None = None
        self.color_wheel: ColorWheelWidget | None = None
        self.mode_stack: QStackedWidget | None = None
        self.color_mode_button: QPushButton | None = None
        self.white_mode_button: QPushButton | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(Spacing.MD)

        header = QHBoxLayout()
        header.setSpacing(Spacing.MD)
        self.swatch = QLabel()
        self.swatch.setFixedSize(36, 36)

        header_text = QVBoxLayout()
        header_text.setSpacing(2)
        name_label = QLabel(light.name)
        name_label.setObjectName("CardTitle")
        name_label.setWordWrap(True)
        self.meta_label = QLabel()
        self.meta_label.setObjectName("CardMeta")
        header_text.addWidget(name_label)
        header_text.addWidget(self.meta_label)

        self.toggle = ToggleSwitch()
        self.toggle.toggled.connect(lambda on: self.powerToggled.emit(self.light_id, on))

        header.addWidget(self.swatch)
        header.addLayout(header_text, 1)
        header.addWidget(self.toggle, 0, Qt.AlignTop)
        layout.addLayout(header)

        brightness_title = QLabel("Brightness")
        brightness_title.setObjectName("SectionLabel")
        self.brightness_slider = QSlider(Qt.Horizontal)
        self.brightness_slider.setObjectName("BrightnessSlider")
        self.brightness_slider.setRange(1, 100)
        self.brightness_slider.setValue(max(1, light.brightness))
        self.brightness_value = QLabel(f"{light.brightness}%")
        self.brightness_value.setObjectName("ValueLabel")
        self.brightness_slider.valueChanged.connect(
            lambda value: self.brightness_value.setText(f"{value}%")
        )
        self.brightness_slider.sliderReleased.connect(
            lambda: self.brightnessChanged.emit(self.light_id, self.brightness_slider.value())
        )
        brightness_row = QHBoxLayout()
        brightness_row.setSpacing(Spacing.SM)
        brightness_row.addWidget(icon_label("sun"))
        brightness_row.addWidget(self.brightness_slider, 1)
        brightness_row.addWidget(self.brightness_value)

        layout.addWidget(brightness_title)
        layout.addLayout(brightness_row)

        if light.supports_color and light.supports_temperature:
            mode_row = QHBoxLayout()
            mode_row.setSpacing(Spacing.SM)
            self.color_mode_button = QPushButton("Color")
            self.white_mode_button = QPushButton("White")
            for button in (self.color_mode_button, self.white_mode_button):
                button.setObjectName("ModeTab")
                button.setCheckable(True)
            self._mode_group = QButtonGroup(self)
            self._mode_group.setExclusive(True)
            self._mode_group.addButton(self.color_mode_button)
            self._mode_group.addButton(self.white_mode_button)
            self.color_mode_button.clicked.connect(lambda: self._set_mode(self.COLOR_MODE_INDEX))
            self.white_mode_button.clicked.connect(lambda: self._set_mode(self.WHITE_MODE_INDEX))
            mode_row.addWidget(self.color_mode_button)
            mode_row.addWidget(self.white_mode_button)
            mode_row.addStretch(1)

            self.mode_stack = QStackedWidget()
            self.mode_stack.addWidget(self._build_color_section())
            self.mode_stack.addWidget(self._build_temperature_section(light))

            layout.addLayout(mode_row)
            layout.addWidget(self.mode_stack)
            self._set_mode(self.WHITE_MODE_INDEX if light.color_mode == "ct" else self.COLOR_MODE_INDEX)
        elif light.supports_color:
            color_title = QLabel("Color")
            color_title.setObjectName("SectionLabel")
            layout.addWidget(color_title)
            layout.addWidget(self._build_color_section())
        elif light.supports_temperature:
            temp_title = QLabel("Temperature")
            temp_title.setObjectName("SectionLabel")
            layout.addWidget(temp_title)
            layout.addWidget(self._build_temperature_section(light))

        layout.addStretch(1)
        self.update_light(light)

    def _build_color_section(self) -> QWidget:
        section = QWidget()
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(0, 0, 0, 0)
        section_layout.setSpacing(Spacing.SM)

        preset_row = QHBoxLayout()
        preset_row.setSpacing(6)
        for name, hex_color in PRESET_COLORS:
            swatch = _preset_swatch_button(hex_color, name, size=22)
            swatch.clicked.connect(
                lambda _=False, c=hex_color: self.colorPicked.emit(self.light_id, QColor(c))
            )
            preset_row.addWidget(swatch)
        preset_row.addStretch(1)

        self.color_wheel = ColorWheelWidget(size=168)
        self.color_wheel.colorCommitted.connect(
            lambda color: self.colorPicked.emit(self.light_id, color)
        )

        section_layout.addLayout(preset_row)
        section_layout.addWidget(self.color_wheel, 0, Qt.AlignHCenter)
        return section

    def _build_temperature_section(self, light: Light) -> QWidget:
        section = QWidget()
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(0, 0, 0, 0)
        section_layout.setSpacing(Spacing.SM)

        self.temperature_slider = QSlider(Qt.Horizontal)
        self.temperature_slider.setObjectName("TemperatureSlider")
        minimum_ct = light.temperature_min or 153
        maximum_ct = light.temperature_max or 500
        current_ct = light.color_temperature or minimum_ct
        self.temperature_slider.setRange(minimum_ct, maximum_ct)
        self.temperature_slider.setValue(current_ct)
        self.temperature_value = QLabel(self._format_temperature(current_ct))
        self.temperature_value.setObjectName("ValueLabel")
        self.temperature_slider.valueChanged.connect(
            lambda value: self.temperature_value.setText(self._format_temperature(value))
        )
        self.temperature_slider.sliderReleased.connect(
            lambda: self.temperatureChanged.emit(self.light_id, self.temperature_slider.value())
        )
        temp_row = QHBoxLayout()
        temp_row.setSpacing(Spacing.SM)
        temp_row.addWidget(icon_label("thermometer"))
        temp_row.addWidget(self.temperature_slider, 1)
        temp_row.addWidget(self.temperature_value)
        section_layout.addLayout(temp_row)
        section_layout.addStretch(1)
        return section

    def _set_mode(self, index: int) -> None:
        if self.mode_stack is None:
            return
        self.mode_stack.setCurrentIndex(index)
        if self.color_mode_button is not None:
            self.color_mode_button.setChecked(index == self.COLOR_MODE_INDEX)
        if self.white_mode_button is not None:
            self.white_mode_button.setChecked(index == self.WHITE_MODE_INDEX)

    @staticmethod
    def _format_temperature(mirek: int | None) -> str:
        return f"{HueBridgeClient.mirek_to_kelvin(mirek)}K"

    def update_light(self, light: Light) -> None:
        self.light_id = light.light_id
        self.setProperty("unreachable", not light.reachable)
        style = self.style()
        style.unpolish(self)
        style.polish(self)

        self.toggle.setEnabled(light.reachable)
        self.toggle.setChecked(light.is_on, animate=False)
        self.meta_label.setText("Online" if light.reachable else "Unavailable")
        self.meta_label.setStyleSheet(
            f"color: {Color.SUCCESS if light.reachable else Color.DANGER};"
        )

        self.brightness_slider.blockSignals(True)
        self.brightness_slider.setValue(max(1, light.brightness))
        self.brightness_slider.blockSignals(False)
        self.brightness_value.setText(f"{light.brightness}%")

        if self.temperature_slider is not None and self.temperature_value is not None:
            current_ct = light.color_temperature or self.temperature_slider.minimum()
            self.temperature_slider.blockSignals(True)
            self.temperature_slider.setValue(current_ct)
            self.temperature_slider.blockSignals(False)
            self.temperature_value.setText(self._format_temperature(current_ct))

        if self.color_wheel is not None and light.xy:
            red, green, blue = HueBridgeClient.xy_to_rgb(light.xy[0], light.xy[1], light.brightness)
            self.color_wheel.set_selected_color(QColor(red, green, blue))

        if self.mode_stack is not None:
            self._set_mode(self.WHITE_MODE_INDEX if light.color_mode == "ct" else self.COLOR_MODE_INDEX)

        self._paint_swatch(light)

    def _paint_swatch(self, light: Light) -> None:
        if not light.is_on:
            fill = QColor(58, 57, 60)
        elif light.supports_color and light.xy and light.color_mode != "ct":
            red, green, blue = HueBridgeClient.xy_to_rgb(light.xy[0], light.xy[1], light.brightness)
            fill = QColor(red, green, blue)
        elif light.supports_temperature and light.color_temperature:
            kelvin = HueBridgeClient.mirek_to_kelvin(light.color_temperature)
            t = max(0.0, min(1.0, (kelvin - 2000) / 4000))
            fill = _blend(QColor(Color.WARM), QColor(Color.COOL), t)
        elif light.supports_color and light.xy:
            red, green, blue = HueBridgeClient.xy_to_rgb(light.xy[0], light.xy[1], light.brightness)
            fill = QColor(red, green, blue)
        else:
            fill = QColor("#f4f2ee")

        size = 36
        canvas = QPixmap(size, size)
        canvas.fill(Qt.transparent)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(255, 255, 255, 30), 1.5))
        painter.setBrush(fill)
        painter.drawEllipse(1, 1, size - 2, size - 2)
        painter.end()
        self.swatch.setPixmap(canvas)
