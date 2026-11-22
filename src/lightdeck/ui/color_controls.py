"""Color + white (temperature) picker used by the light panel and scene editor."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from .. import colors
from .widgets import ColorWheel, Segmented, TemperatureSlider, label

COLOR_PRESETS = [
    ("Red", 0, 1.0), ("Orange", 28, 1.0), ("Yellow", 50, 0.95), ("Green", 120, 0.9),
    ("Cyan", 185, 0.85), ("Blue", 228, 1.0), ("Purple", 275, 0.9), ("Pink", 320, 0.75),
]
WHITE_PRESETS = [("Relax", 447), ("Read", 346), ("Concentrate", 233), ("Energize", 156)]


class _Swatch(QPushButton):
    def __init__(self, name: str, color: QColor) -> None:
        super().__init__()
        self.setToolTip(name)
        self.setFixedSize(26, 26)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            f"QPushButton {{ background: {color.name()}; border-radius: 13px; border: 2px solid rgba(0,0,0,0.12); }}"
            f"QPushButton:hover {{ border: 2px solid rgba(255,255,255,0.8); }}"
        )


class ColorControls(QWidget):
    xyChanged = Signal(float, float)
    mirekChanged = Signal(int)

    COLOR, WHITE = 0, 1

    def __init__(self, wheel_size: int = 232, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._gamut: colors.Gamut | None = colors.GAMUT_C
        self._mirek_min, self._mirek_max = colors.MIREK_MIN, colors.MIREK_MAX
        self._has_color = self._has_ct = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        self.mode = Segmented(["Color", "White"])
        self.mode.changed.connect(self._on_mode_clicked)
        layout.addWidget(self.mode, 0, Qt.AlignLeft)

        self.stack = QStackedWidget()
        layout.addWidget(self.stack)

        # Color page
        color_page = QWidget()
        color_layout = QVBoxLayout(color_page)
        color_layout.setContentsMargins(0, 0, 0, 0)
        color_layout.setSpacing(14)
        self.wheel = ColorWheel(wheel_size)
        self.wheel.colorChanged.connect(self._emit_xy)
        color_layout.addWidget(self.wheel, 0, Qt.AlignHCenter)
        swatches = QHBoxLayout()
        swatches.setSpacing(8)
        swatches.addStretch(1)
        for name, hue, sat in COLOR_PRESETS:
            swatch = _Swatch(name, QColor.fromHsvF(hue / 360, sat, 1.0))
            swatch.clicked.connect(lambda _=False, h=hue, s=sat: self._pick_hs(h, s))
            swatches.addWidget(swatch)
        swatches.addStretch(1)
        color_layout.addLayout(swatches)
        self.stack.addWidget(color_page)

        # White page
        white_page = QWidget()
        white_layout = QVBoxLayout(white_page)
        white_layout.setContentsMargins(0, 0, 0, 0)
        white_layout.setSpacing(12)
        white_layout.addWidget(label("Color temperature", "FieldLabel"))
        self.temperature = TemperatureSlider()
        self.temperature.mirekChanged.connect(self.mirekChanged.emit)
        white_layout.addWidget(self.temperature)
        ends = QHBoxLayout()
        ends.addWidget(label("Warm", "Hint"))
        ends.addStretch(1)
        ends.addWidget(label("Cool", "Hint"))
        white_layout.addLayout(ends)
        chips = QGridLayout()
        chips.setSpacing(6)
        for index, (name, mirek) in enumerate(WHITE_PRESETS):
            chip = QPushButton(name)
            chip.setObjectName("Chip")
            chip.setCursor(Qt.PointingHandCursor)
            chip.clicked.connect(lambda _=False, m=mirek: self._pick_mirek(m))
            chips.addWidget(chip, index // 2, index % 2)
        white_layout.addLayout(chips)
        white_layout.addStretch(1)
        self.stack.addWidget(white_page)

    # -- configuration -----------------------------------------------------

    def configure(self, *, has_color: bool, has_ct: bool, gamut: colors.Gamut | None,
                  mirek_min: int, mirek_max: int) -> None:
        self._has_color, self._has_ct = has_color, has_ct
        self._gamut = gamut
        if (mirek_min, mirek_max) != (self._mirek_min, self._mirek_max):
            self._mirek_min, self._mirek_max = mirek_min, mirek_max
            self.temperature.set_range_mirek(mirek_min, mirek_max)
        self.mode.setVisible(has_color and has_ct)
        self.setVisible(has_color or has_ct)
        if not has_color:
            self.stack.setCurrentIndex(self.WHITE)
        elif not has_ct:
            self.stack.setCurrentIndex(self.COLOR)

    def set_state(self, mode: str, xy: colors.XY | None, mirek: int | None) -> None:
        if self.wheel.isDragging() or self.temperature.isDragging():
            return
        index = self.WHITE if (mode == "ct" or not self._has_color) and self._has_ct else self.COLOR
        self.stack.setCurrentIndex(index)
        self.mode.set_index(index)
        if xy:
            self.wheel.set_hs(*colors.xy_to_hs(*xy))
        if mirek:
            self.temperature.set_mirek(mirek)

    def is_interacting(self) -> bool:
        return self.wheel.isDragging() or self.temperature.isDragging()

    # -- events ------------------------------------------------------------

    def _emit_xy(self, hue: float, saturation: float) -> None:
        x, y = colors.hs_to_xy(hue, saturation, self._gamut)
        self.xyChanged.emit(x, y)

    def _pick_hs(self, hue: float, saturation: float) -> None:
        self.wheel.set_hs(hue, saturation)
        self._emit_xy(hue, saturation)

    def _pick_mirek(self, mirek: int) -> None:
        mirek = max(self._mirek_min, min(self._mirek_max, mirek))
        self.temperature.set_mirek(mirek)
        self.mirekChanged.emit(mirek)

    def _on_mode_clicked(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        if index == self.COLOR:
            color = self.wheel.color()
            self._emit_xy(color.hsvHueF() * 360, color.hsvSaturationF())
        else:
            self.mirekChanged.emit(max(self._mirek_min, min(self._mirek_max, colors.kelvin_to_mirek(self.temperature.value()))))
