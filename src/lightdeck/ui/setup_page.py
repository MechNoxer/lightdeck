"""First-run flow: find a bridge, press its link button, done."""

from __future__ import annotations

import ipaddress
import socket
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import APP_ID, APP_NAME
from ..hue.client import (
    DiscoveredBridge,
    HueClient,
    HueError,
    LinkButtonNotPressedError,
    bridge_info,
    discover_bridges,
    fetch_fingerprint,
)
from ..hue.controller import TaskRunner
from . import icons, theme
from .widgets import Spinner, button, label

PAIR_SECONDS = 30


class CountdownRing(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(132, 132)
        self.progress = 1.0

    def set_progress(self, value: float) -> None:
        self.progress = max(0.0, min(1.0, value))
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        p = theme.current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(6, 6, -6, -6)
        painter.setPen(QPen(theme.qcolor(p.track), 6))
        painter.drawEllipse(rect)
        painter.setPen(QPen(theme.qcolor(p.accent), 6, Qt.SolidLine, Qt.RoundCap))
        painter.drawArc(rect, 90 * 16, int(-360 * 16 * self.progress))
        inner = rect.adjusted(26, 26, -26, -26)
        painter.setPen(Qt.NoPen)
        painter.setBrush(theme.qcolor(p.surface_alt))
        painter.drawEllipse(inner)
        painter.drawPixmap(QPointF(inner.center().x() - 18, inner.center().y() - 18), icons.pixmap("router", p.text, 36))


class SetupPage(QWidget):
    paired = Signal(object, str, str, str)  # bridge, app key, client key, cert fingerprint
    demoRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.tasks = TaskRunner(self)
        self._pair_token = 0
        self._deadline = 0.0
        self._bridge: DiscoveredBridge | None = None
        self._fingerprint = ""
        self._searching = False

        card = QFrame()
        card.setObjectName("Panel")
        card.setFixedWidth(500)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(32, 30, 32, 28)
        card_layout.setSpacing(0)
        self.stack = QStackedWidget()
        card_layout.addWidget(self.stack)
        self.stack.addWidget(self._build_discover())
        self.stack.addWidget(self._build_pair())

        outer = QVBoxLayout(self)
        outer.addStretch(1)
        brand = QHBoxLayout()
        brand.addStretch(1)
        title = label(f"Welcome to {APP_NAME}", "PageTitle")
        brand.addWidget(title)
        brand.addStretch(1)
        outer.addLayout(brand)
        sub = QHBoxLayout()
        sub.addStretch(1)
        sub.addWidget(label("Control your lights, rooms and scenes from your desktop.", "PageSubtitle"))
        sub.addStretch(1)
        outer.addLayout(sub)
        outer.addSpacing(24)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(card)
        row.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(2)

        self._tick = QTimer(self)
        self._tick.setInterval(50)
        self._tick.timeout.connect(self._update_countdown)

    # -- views -------------------------------------------------------------

    def _build_discover(self) -> QWidget:
        view = QWidget()
        layout = QVBoxLayout(view)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(label("Connect your bridge", "SectionTitle"))
        layout.addWidget(label("Make sure your computer is on the same network as your Hue Bridge.", "Muted", True))
        layout.addSpacing(6)

        self.bridge_list = QVBoxLayout()
        self.bridge_list.setSpacing(8)
        layout.addLayout(self.bridge_list)

        status = QHBoxLayout()
        status.setSpacing(8)
        self.spinner = Spinner()
        self.status = label("", "Muted", True)
        self.rescan = button("Search again", "Ghost", "refresh")
        self.rescan.clicked.connect(self.start_discovery)
        status.addWidget(self.spinner)
        status.addWidget(self.status, 1)
        status.addWidget(self.rescan)
        layout.addLayout(status)

        layout.addSpacing(10)
        layout.addWidget(label("Or enter the bridge's IP address", "FieldLabel"))
        manual = QHBoxLayout()
        self.ip_field = QLineEdit()
        self.ip_field.setPlaceholderText("192.168.1.20")
        self.ip_field.returnPressed.connect(self._connect_manual)
        self.connect_button = button("Connect", "Primary")
        self.connect_button.clicked.connect(self._connect_manual)
        manual.addWidget(self.ip_field, 1)
        manual.addWidget(self.connect_button)
        layout.addLayout(manual)

        self.error = label("", "CardMeta", True)
        self.error.setProperty("warn", True)
        self.error.hide()
        layout.addWidget(self.error)

        layout.addSpacing(12)
        demo = button("No bridge handy? Try the demo", "Ghost", "sparkles")
        demo.clicked.connect(self.demoRequested.emit)
        layout.addWidget(demo, 0, Qt.AlignLeft)
        return view

    def _build_pair(self) -> QWidget:
        view = QWidget()
        layout = QVBoxLayout(view)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(12)
        self.ring = CountdownRing()
        layout.addWidget(self.ring, 0, Qt.AlignHCenter)
        layout.addSpacing(6)
        title = label("Press the link button", "SectionTitle")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        self.pair_text = label("", "Muted", True)
        self.pair_text.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.pair_text)
        layout.addSpacing(8)
        cancel = button("Cancel", "Ghost")
        cancel.clicked.connect(self._cancel_pairing)
        layout.addWidget(cancel, 0, Qt.AlignHCenter)
        return view

    # -- discovery ---------------------------------------------------------

    def reset(self, message: str = "") -> None:
        self._pair_token += 1
        self._tick.stop()
        self.stack.setCurrentIndex(0)
        self._show_error(message)
        self.start_discovery()

    def _show_error(self, message: str) -> None:
        self.error.setText(message)
        self.error.setVisible(bool(message))

    def start_discovery(self) -> None:
        if self._searching:
            return
        self._searching = True
        self.spinner.start()
        self.rescan.setEnabled(False)
        self.status.setText("Searching your network…")
        self.tasks.run(discover_bridges, self._on_discovered, self._on_discovery_failed)

    def _clear_bridges(self) -> None:
        while self.bridge_list.count():
            widget = self.bridge_list.takeAt(0).widget()
            if widget:
                widget.deleteLater()

    def _on_discovered(self, bridges: list[DiscoveredBridge]) -> None:
        self._searching = False
        self.spinner.stop()
        self.rescan.setEnabled(True)
        self._clear_bridges()
        for bridge in bridges:
            row = QPushButton(f"{bridge.name}\n{bridge.ip}" + ("" if bridge.supports_v2 else " · needs a firmware update"))
            row.setObjectName("BridgeRow")
            row.setCursor(Qt.PointingHandCursor)
            row.setIcon(icons.icon("router", theme.current().text, 22))
            row.setEnabled(bridge.supports_v2)
            row.clicked.connect(lambda _=False, b=bridge: self._start_pairing(b))
            self.bridge_list.addWidget(row)
        if bridges:
            self.status.setText(f"Found {len(bridges)} bridge{'s' if len(bridges) != 1 else ''}. Pick one to pair.")
        else:
            self.status.setText("No bridges found automatically.")

    def _on_discovery_failed(self, exc: Exception) -> None:
        self._on_discovered([])
        self.status.setText(f"Search failed: {exc}")

    def _connect_manual(self) -> None:
        text = self.ip_field.text().strip()
        try:
            ipaddress.ip_address(text)
        except ValueError:
            self._show_error("Enter an IP address like 192.168.1.20.")
            return
        self._show_error("")
        self.connect_button.setEnabled(False)

        def done(bridge: DiscoveredBridge) -> None:
            self.connect_button.setEnabled(True)
            if not bridge.supports_v2:
                self._show_error("This bridge needs a firmware update in the Hue app before it can be used.")
                return
            self._start_pairing(bridge)

        def failed(exc: Exception) -> None:
            self.connect_button.setEnabled(True)
            self._show_error(str(exc))

        self.tasks.run(lambda: bridge_info(text), done, failed)

    # -- pairing -----------------------------------------------------------

    def _start_pairing(self, bridge: DiscoveredBridge) -> None:
        self._bridge = bridge
        self._pair_token += 1
        token = self._pair_token
        self._show_error("")
        self.stack.setCurrentIndex(1)
        self.ring.set_progress(1.0)
        self.pair_text.setText(f"Connecting to {bridge.name}…")

        def got_fingerprint(fingerprint: str) -> None:
            if token != self._pair_token:
                return
            self._fingerprint = fingerprint
            self._deadline = time.monotonic() + PAIR_SECONDS
            self._tick.start()
            self._attempt(token)

        self.tasks.run(lambda: fetch_fingerprint(bridge.ip), got_fingerprint,
                       lambda exc: token == self._pair_token and self.reset(str(exc)))

    def _attempt(self, token: int) -> None:
        if token != self._pair_token or self._bridge is None:
            return
        bridge, fingerprint = self._bridge, self._fingerprint
        device = f"{APP_ID}#{socket.gethostname()[:19]}"

        def done(keys: tuple[str, str]) -> None:
            if token != self._pair_token:
                return
            self._tick.stop()
            self.paired.emit(bridge, keys[0], keys[1], fingerprint)

        def failed(exc: Exception) -> None:
            if token != self._pair_token:
                return
            if isinstance(exc, LinkButtonNotPressedError) and time.monotonic() < self._deadline:
                QTimer.singleShot(1000, lambda: self._attempt(token))
            elif isinstance(exc, LinkButtonNotPressedError):
                self.reset("Timed out waiting for the link button. Try again.")
            else:
                self.reset(str(exc) if isinstance(exc, HueError) else f"Pairing failed: {exc}")

        self.tasks.run(lambda: HueClient.pair(bridge.ip, fingerprint, device), done, failed)

    def _update_countdown(self) -> None:
        remaining = max(0.0, self._deadline - time.monotonic())
        self.ring.set_progress(remaining / PAIR_SECONDS)
        name = self._bridge.name if self._bridge else "your bridge"
        self.pair_text.setText(
            f"Press the round button on top of {name}.\nWaiting for {int(remaining) + 1} more seconds…"
        )

    def _cancel_pairing(self) -> None:
        self._pair_token += 1
        self._tick.stop()
        self.stack.setCurrentIndex(0)
