"""Top-level window: setup flow or the main shell, plus bridge lifecycle."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QStackedWidget, QWidget

from .. import APP_NAME
from ..config import AppConfig, save_config
from ..hue.client import DiscoveredBridge, HueClient, fetch_fingerprint
from ..hue.controller import HueController, TaskRunner
from ..hue.demo import DemoClient
from .pages import HomePage, RoomPage, SettingsPage
from .setup_page import SetupPage
from .sidebar import Sidebar
from .theme import ThemeManager
from .widgets import ToastHost, refresh_icon_buttons, rgb_qcolor

ASSETS = Path(__file__).resolve().parent.parent / "assets"


def app_icon() -> QIcon:
    path = ASSETS / "lightdeck.png"
    return QIcon(str(path)) if path.exists() else QIcon()


class MainWindow(QMainWindow):
    SETUP, SHELL = 0, 1
    HOME, ROOM, SETTINGS = 0, 1, 2

    def __init__(self, config: AppConfig, themes: ThemeManager, demo: bool = False) -> None:
        super().__init__()
        self.config = config
        self.themes = themes
        self.controller: HueController | None = None
        self.demo = False
        self.tasks = TaskRunner(self)

        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        self.resize(1200, 800)
        self.setMinimumSize(900, 600)

        self.root = QStackedWidget()
        self.root.setObjectName("AppRoot")
        self.setup = SetupPage()
        self.setup.paired.connect(self._on_paired)
        self.setup.demoRequested.connect(self.start_demo)
        self.root.addWidget(self.setup)

        shell = QWidget()
        shell_layout = QHBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)
        self.sidebar = Sidebar()
        self.sidebar.set_logo(QPixmap(str(ASSETS / "lightdeck.png")))
        self.sidebar.navigate.connect(self.navigate)
        self.content = QStackedWidget()
        self.home = HomePage()
        self.home.openGroup.connect(self.navigate)
        self.room = RoomPage()
        self.settings = SettingsPage()
        self.settings.set_theme(config.theme)
        self.settings.themeChanged.connect(self._set_theme)
        self.settings.forgetRequested.connect(self.forget_bridge)
        self.settings.reconnectRequested.connect(lambda: self.controller and self.controller.reload())
        for page in (self.home, self.room, self.settings):
            self.content.addWidget(page)
        shell_layout.addWidget(self.sidebar)
        shell_layout.addWidget(self.content, 1)
        self.root.addWidget(shell)
        self.setCentralWidget(self.root)
        self.toasts = ToastHost(self.root)
        themes.changed.connect(self._on_theme_changed)

        if demo:
            self.start_demo()
        elif config.is_paired:
            self.connect_saved_bridge()
        else:
            self.show_setup()

    # -- navigation --------------------------------------------------------

    def show_setup(self, message: str = "") -> None:
        self.root.setCurrentIndex(self.SETUP)
        self.setup.reset(message)

    def navigate(self, key: str) -> None:
        self.sidebar.set_current(key)
        if key == "home":
            self.content.setCurrentIndex(self.HOME)
            self.home.refresh()
        elif key == "settings":
            self.content.setCurrentIndex(self.SETTINGS)
        else:
            self.room.show_group(key)
            self.content.setCurrentIndex(self.ROOM)

    # -- bridge lifecycle --------------------------------------------------

    def connect_saved_bridge(self) -> None:
        if self.config.cert_sha256:
            self._start(HueClient(self.config.bridge_ip, self.config.app_key, self.config.cert_sha256))
            return
        # Pairings migrated from older versions have no pinned certificate yet.
        def pinned(fingerprint: str) -> None:
            self.config.cert_sha256 = fingerprint
            save_config(self.config)
            self.connect_saved_bridge()

        self.root.setCurrentIndex(self.SHELL)
        self.sidebar.set_status(False, "Connecting…")
        self.tasks.run(
            lambda: fetch_fingerprint(self.config.bridge_ip), pinned,
            lambda exc: self.show_setup(f"Couldn't reach your bridge at {self.config.bridge_ip}: {exc}"),
        )

    def start_demo(self) -> None:
        self.demo = True
        self._start(DemoClient())
        self.toasts.show_message("Demo mode: changes only affect simulated lights.")

    def _on_paired(self, bridge: DiscoveredBridge, app_key: str, client_key: str, fingerprint: str) -> None:
        self.config.bridge_ip = bridge.ip
        self.config.bridge_id = bridge.bridge_id
        self.config.bridge_name = bridge.name
        self.config.app_key = app_key
        self.config.client_key = client_key
        self.config.cert_sha256 = fingerprint
        save_config(self.config)
        self.demo = False
        self._start(HueClient(bridge.ip, app_key, fingerprint))
        self.toasts.show_message(f"Paired with {bridge.name}.", "success")

    def _start(self, client) -> None:
        self._stop()
        controller = HueController(client, self)
        controller.store.changed.connect(self._refresh)
        controller.loaded.connect(self._on_loaded)
        controller.error.connect(lambda msg: self.toasts.show_message(msg, "error"))
        controller.unauthorized.connect(self._on_unauthorized)
        controller.connectionChanged.connect(self._on_connection)
        self.controller = controller
        for page in (self.home, self.room):
            page.set_controller(controller)
        self.sidebar.set_status(False, "Connecting…")
        self.root.setCurrentIndex(self.SHELL)
        self.navigate("home")
        controller.start()

    def _stop(self) -> None:
        if self.controller is not None:
            self.controller.stop()
            self.controller.deleteLater()
            self.controller = None
        for page in (self.home, self.room):
            page.set_controller(None)

    def _on_loaded(self) -> None:
        self._refresh()

    def _on_connection(self, connected: bool) -> None:
        self._update_status()
        if not connected and self.controller and self.controller.store.loaded:
            self.toasts.show_message("Lost connection to the bridge. Reconnecting…", "error")

    def _on_unauthorized(self) -> None:
        self.forget_bridge(silent=True)
        self.show_setup("The bridge no longer recognizes this app. Pair it again.")

    def forget_bridge(self, silent: bool = False) -> None:
        self._stop()
        if not self.demo:
            self.config.forget_bridge()
            save_config(self.config)
        self.demo = False
        self.show_setup()

    def _update_status(self) -> None:
        if not self.controller:
            return
        store = self.controller.store
        name = "Demo bridge" if self.demo else (store.bridge_name() if store.loaded else self.config.bridge_name or "Bridge")
        connected = self.controller.connected
        self.sidebar.set_status(connected, name if connected else f"{name} · offline")
        details = "Simulated lights — nothing on your network is changed." if self.demo else (
            f"IP address: {self.config.bridge_ip}\nBridge ID: {self.config.bridge_id or 'unknown'}\n"
            f"Status: {'connected' if connected else 'reconnecting…'}"
        )
        self.settings.set_bridge(name, details, self.demo)

    def _refresh(self) -> None:
        if not self.controller:
            return
        store = self.controller.store
        rooms, zones = store.groups("room"), store.groups("zone")
        lit: dict[str, object] = {}
        for group in rooms + zones:
            on = [l for l in store.group_lights(group) if l.on and l.reachable]
            lit[group.id] = rgb_qcolor(on[0].rgb) if on else None
        self.sidebar.set_groups(rooms, zones, lit)
        current = self.sidebar.current()
        if current not in ("home", "settings") and current is not None and store.group(current) is None:
            self.navigate("home")
        self.home.refresh()
        if self.content.currentIndex() == self.ROOM:
            self.room.refresh()
        self._update_status()

    # -- theme -------------------------------------------------------------

    def _set_theme(self, mode: str) -> None:
        self.config.theme = mode
        save_config(self.config)
        self.themes.set_mode(mode)

    def _on_theme_changed(self) -> None:
        refresh_icon_buttons(self)
        self._update_status()
        self._refresh()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._stop()
        super().closeEvent(event)
