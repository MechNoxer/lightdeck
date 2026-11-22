"""Left navigation: home, rooms, zones, settings and bridge status."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QAbstractButton, QButtonGroup, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .. import APP_NAME
from ..hue.models import GroupView
from . import icons, theme
from .widgets import label


class NavItem(QAbstractButton):
    def __init__(self, key: str, text: str, icon_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.key = key
        self.icon_name = icon_name
        self.setText(text)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        self.setFixedHeight(36)
        self.dot: QColor | None = None

    def set_dot(self, color: QColor | None) -> None:
        if color != self.dot:
            self.dot = color
            self.update()

    def sizeHint(self) -> QSize:  # type: ignore[override]
        return QSize(200, 36)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        p = theme.current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0, 1, 0, -1)
        if self.isChecked():
            painter.setPen(Qt.NoPen)
            painter.setBrush(theme.qcolor(p.accent_soft))
            painter.drawRoundedRect(rect, 9, 9)
        elif self.underMouse():
            painter.setPen(Qt.NoPen)
            painter.setBrush(theme.qcolor(p.surface_hover))
            painter.drawRoundedRect(rect, 9, 9)
        color = p.accent if self.isChecked() else p.text_secondary
        painter.drawPixmap(QPointF(rect.left() + 12, rect.center().y() - 9), icons.pixmap(self.icon_name, color, 18))
        font = QFont(self.font())
        font.setWeight(QFont.DemiBold if self.isChecked() else QFont.Medium)
        painter.setFont(font)
        painter.setPen(theme.qcolor(p.text if self.isChecked() else p.text_secondary))
        text_rect = rect.adjusted(40, 0, -30, 0)
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft,
                         painter.fontMetrics().elidedText(self.text(), Qt.ElideRight, int(text_rect.width())))
        if self.dot is not None:
            painter.setPen(Qt.NoPen)
            painter.setBrush(self.dot)
            painter.drawEllipse(QPointF(rect.right() - 16, rect.center().y()), 4.5, 4.5)


class Sidebar(QFrame):
    navigate = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(236)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._items: dict[str, NavItem] = {}
        self._signature: tuple = ()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 18, 12, 14)
        layout.setSpacing(2)

        brand = QHBoxLayout()
        brand.setContentsMargins(8, 0, 0, 14)
        brand.setSpacing(10)
        self.logo = QLabel()
        self.logo.setFixedSize(28, 28)
        brand.addWidget(self.logo)
        brand.addWidget(label(APP_NAME, "BrandName"))
        brand.addStretch(1)
        layout.addLayout(brand)

        self.home = self._make_item("home", "Home", "home")
        layout.addWidget(self.home)
        self.dynamic = QVBoxLayout()
        self.dynamic.setSpacing(2)
        layout.addLayout(self.dynamic)
        layout.addStretch(1)

        status = QHBoxLayout()
        status.setContentsMargins(10, 8, 8, 8)
        status.setSpacing(8)
        self.status_dot = QLabel()
        self.status_dot.setFixedSize(8, 8)
        self.status_text = label("", "StatusText")
        status.addWidget(self.status_dot)
        status.addWidget(self.status_text, 1)
        layout.addLayout(status)
        layout.addWidget(self._make_item("settings", "Settings", "settings"))

    def set_logo(self, pixmap) -> None:
        if pixmap is not None and not pixmap.isNull():
            self.logo.setPixmap(pixmap.scaled(28, 28, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _make_item(self, key: str, text: str, icon_name: str) -> NavItem:
        item = NavItem(key, text, icon_name)
        item.clicked.connect(lambda: self.navigate.emit(key))
        self._group.addButton(item)
        self._items[key] = item
        return item

    def set_groups(self, rooms: list[GroupView], zones: list[GroupView], lit: dict[str, QColor | None]) -> None:
        signature = tuple((g.id, g.name) for g in rooms) + ("|",) + tuple((g.id, g.name) for g in zones)
        if signature != self._signature:
            self._signature = signature
            current = self.current()
            while self.dynamic.count():
                widget = self.dynamic.takeAt(0).widget()
                if widget is None:
                    continue
                if isinstance(widget, NavItem):
                    self._group.removeButton(widget)
                    self._items.pop(widget.key, None)
                widget.deleteLater()
            for title, groups, icon_name in (("ROOMS", rooms, "room"), ("ZONES", zones, "zone")):
                if not groups:
                    continue
                self.dynamic.addWidget(label(title, "NavSection"))
                for group in groups:
                    self.dynamic.addWidget(self._make_item(group.id, group.name, icon_name))
            if current:
                self.set_current(current)
        for key, color in lit.items():
            item = self._items.get(key)
            if item:
                item.set_dot(color)

    def current(self) -> str | None:
        checked = self._group.checkedButton()
        return checked.key if isinstance(checked, NavItem) else None

    def set_current(self, key: str) -> None:
        item = self._items.get(key)
        if item:
            item.setChecked(True)

    def set_status(self, connected: bool, text: str) -> None:
        p = theme.current()
        color = p.success if connected else p.danger
        self.status_dot.setStyleSheet(f"background: {color}; border-radius: 4px;")
        self.status_text.setText(text)
