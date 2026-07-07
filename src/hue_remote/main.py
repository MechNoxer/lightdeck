from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QWidget,
)

from .config import BridgeConfig, load_config, save_config
from .hue_api import Bridge, HueBridgeClient, Light
from .pages import HomePage, HubPage, Sidebar
from .theme import Color, build_stylesheet


class WorkerSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class Worker(QRunnable):
    def __init__(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as exc:  # noqa: BLE001
            self.signals.failed.emit(str(exc))
            return
        self.signals.finished.emit(result)


class HueRemoteWindow(QMainWindow):
    HOME_PAGE = 0
    HUB_PAGE = 1

    @staticmethod
    def app_icon() -> QIcon:
        icon_path = Path(__file__).resolve().parent / "assets" / "philips-hue-for-arch.png"
        if icon_path.exists():
            return QIcon(str(icon_path))
        return QIcon()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("philips-hue-for-arch")
        icon = self.app_icon()
        if not icon.isNull():
            self.setWindowIcon(icon)
        self.resize(1120, 760)
        self.setMinimumSize(920, 640)

        self.thread_pool = QThreadPool()
        self.bridge_config = load_config()
        self.client = HueBridgeClient(
            bridge_ip=self.bridge_config.bridge_ip,
            username=self.bridge_config.username,
        )

        self.current_lights: dict[str, Light] = {}
        self.discovered_bridges: list[Bridge] = []
        self.selected_bridge: Bridge | None = None
        self.pair_poll_attempts_remaining = 0
        self.active_workers: set[Worker] = set()
        self.light_operation_in_flight = False
        self.refresh_request_token = 0

        self.sidebar = Sidebar()
        self.home_page = HomePage()
        self.hub_page = HubPage()

        self.stack = QStackedWidget()
        self.stack.addWidget(self.home_page)
        self.stack.addWidget(self.hub_page)

        shell = QWidget()
        shell_layout = QHBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)
        shell_layout.addWidget(self.sidebar)
        shell_layout.addWidget(self.stack, 1)
        self.setCentralWidget(shell)

        self.apply_styles()
        self.connect_signals()

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_lights)
        self.refresh_timer.start(15000)

        self.pair_poll_timer = QTimer(self)
        self.pair_poll_timer.setSingleShot(True)
        self.pair_poll_timer.timeout.connect(self.try_pair_bridge)

        self.update_bridge_summary()
        self.refresh_hub_steps()
        if self.client.is_configured():
            self.show_home_page()
            self.set_status("Bridge paired. Loading lights...")
            self.refresh_lights()
        else:
            self.show_hub_page()
            self.set_hub_status("Add a hub to get started.")

    def connect_signals(self) -> None:
        self.sidebar.lightsRequested.connect(self.show_home_page)
        self.sidebar.addHubRequested.connect(self.open_add_hub_flow)
        self.sidebar.refreshRequested.connect(self.refresh_lights)
        self.sidebar.forgetRequested.connect(self.forget_hub)

        self.home_page.refreshRequested.connect(self.refresh_lights)
        self.home_page.addHubRequested.connect(self.open_add_hub_flow)
        self.home_page.forgetRequested.connect(self.forget_hub)
        self.home_page.allOnRequested.connect(lambda: self.set_all_power(True))
        self.home_page.allOffRequested.connect(lambda: self.set_all_power(False))
        self.home_page.lightPowerToggled.connect(self.handle_power_toggle)
        self.home_page.lightBrightnessChanged.connect(self.change_brightness)
        self.home_page.lightTemperatureChanged.connect(self.change_temperature)
        self.home_page.lightColorPicked.connect(self.handle_color_picked)

        self.hub_page.discoverRequested.connect(self.discover_bridges)
        self.hub_page.pairRequested.connect(self.pair_bridge)
        self.hub_page.backRequested.connect(self.back_to_home)
        self.hub_page.bridgeSelected.connect(self.on_bridge_selected)

    def apply_styles(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.setFont(QFont("Segoe UI", 10))
            palette = QPalette()
            palette.setColor(QPalette.Window, QColor(Color.BG))
            palette.setColor(QPalette.WindowText, QColor(Color.TEXT_PRIMARY))
            palette.setColor(QPalette.Base, QColor("#202020"))
            palette.setColor(QPalette.Text, QColor(Color.TEXT_PRIMARY))
            palette.setColor(QPalette.ButtonText, QColor(Color.TEXT_PRIMARY))
            app.setPalette(palette)

        self.setStyleSheet(build_stylesheet())

    def run_task(
        self,
        fn: Callable[..., Any],
        on_success: Callable[[Any], None],
        *,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        worker = Worker(fn)
        self.active_workers.add(worker)

        def finish(result: Any) -> None:
            self.active_workers.discard(worker)
            on_success(result)

        def fail(message: str) -> None:
            self.active_workers.discard(worker)
            (on_error or self.show_error)(message)

        worker.signals.finished.connect(finish)
        worker.signals.failed.connect(fail)
        self.thread_pool.start(worker)

    def show_home_page(self) -> None:
        self.stack.setCurrentIndex(self.HOME_PAGE)
        self.sidebar.set_active(True)

    def show_hub_page(self) -> None:
        self.stack.setCurrentIndex(self.HUB_PAGE)
        self.sidebar.set_active(False)

    def set_status(self, message: str) -> None:
        self.home_page.set_status(message)

    def set_hub_status(self, message: str) -> None:
        self.hub_page.set_status(message)
        lowered = message.lower()
        if "looking" in lowered or "discover" in lowered:
            self.hub_page.set_discovery_badge("Scanning")
        elif "waiting" in lowered:
            self.hub_page.set_discovery_badge("Waiting")
        else:
            self.hub_page.set_discovery_badge("Ready")
        self.refresh_hub_steps()

    def refresh_hub_steps(self) -> None:
        discover_state = "done" if self.discovered_bridges else "active"

        if self.selected_bridge is not None:
            select_state = "done"
        elif self.discovered_bridges:
            select_state = "active"
        else:
            select_state = "pending"

        if self.selected_bridge is not None and self.client.is_configured():
            pair_state = "done"
        elif self.pair_poll_attempts_remaining > 0 or self.selected_bridge is not None:
            pair_state = "active"
        else:
            pair_state = "pending"

        self.hub_page.set_step_states(discover_state, select_state, pair_state)

    def show_error(self, message: str) -> None:
        if self.stack.currentIndex() == self.HUB_PAGE:
            self.set_hub_status(message)
        else:
            self.set_status(message)
        QMessageBox.warning(self, "philips-hue-for-arch", message)

    def handle_task_error(self, message: str) -> None:
        self.set_controls_enabled(True)
        self.light_operation_in_flight = False
        if "unauthorized user" in message.lower():
            self.clear_saved_pairing()
            self.current_lights.clear()
            self.home_page.clear_lights()
            self.show_hub_page()
            self.set_hub_status(
                "The saved bridge pairing is no longer valid. Discover the bridge again, then press Pair Bridge."
            )
            return
        self.show_error(message)

    def persist_config(self) -> None:
        save_config(
            BridgeConfig(
                bridge_ip=self.client.bridge_ip,
                username=self.client.username,
            )
        )
        self.update_bridge_summary()

    def update_bridge_summary(self) -> None:
        if self.client.bridge_ip:
            self.sidebar.set_summary(f"Hue Bridge\n{self.client.bridge_ip}")
            self.home_page.set_bridge_badge(self.client.bridge_ip)
            self.home_page.set_home_meta(
                f"Bridge IP: {self.client.bridge_ip}\n"
                f"Pairing: {'active' if self.client.username else 'not paired'}"
            )
        else:
            self.sidebar.set_summary("No Hue bridge paired yet.")
            self.home_page.set_bridge_badge("No hub")
            self.home_page.set_home_meta("No Hue bridge paired.")

    def open_add_hub_flow(self) -> None:
        self.show_hub_page()
        self.set_hub_status("Discover a bridge to begin pairing.")

    def back_to_home(self) -> None:
        if self.client.is_configured():
            self.show_home_page()
            self.set_status("Ready.")
        else:
            self.set_hub_status("Add a hub to continue.")

    def discover_bridges(self) -> None:
        self.selected_bridge = None
        self.hub_page.populate_bridges([])
        self.hub_page.set_bridge_details("Searching for bridges on your network...")
        self.hub_page.set_pair_button_enabled(False)
        self.set_hub_status("Looking for Hue bridges...")
        self.run_task(self.client.discover_bridges, self.on_bridges_discovered, on_error=self.handle_task_error)

    def on_bridges_discovered(self, bridges: list[Bridge]) -> None:
        self.discovered_bridges = bridges
        self.hub_page.populate_bridges(bridges)
        self.hub_page.set_discovery_badge(f"{len(bridges)} found")
        if bridges:
            self.hub_page.bridge_selector.setCurrentIndex(0)
            self.set_hub_status("Bridge found. Click Pair Bridge, then press the physical bridge button.")
        else:
            self.hub_page.set_bridge_details("No bridge selected yet.")
            self.hub_page.set_pair_button_enabled(False)
        self.refresh_hub_steps()

    def on_bridge_selected(self, index: int) -> None:
        if index < 0:
            self.selected_bridge = None
            self.hub_page.set_pair_button_enabled(False)
            self.hub_page.set_bridge_details("No bridge selected yet.")
            self.refresh_hub_steps()
            return
        bridge = self.hub_page.current_bridge()
        if bridge is None:
            return
        self.selected_bridge = bridge
        self.hub_page.set_pair_button_enabled(True)
        self.hub_page.set_bridge_details(
            f"Selected bridge\n\n"
            f"IP address: {bridge.ip_address}\n"
            f"Bridge ID: {bridge.bridge_id}\n\n"
            f"Click Pair Bridge and press the physical button on this bridge."
        )
        self.refresh_hub_steps()

    def pair_bridge(self) -> None:
        if self.selected_bridge is None:
            self.show_error("Select a bridge first.")
            return
        self.client.bridge_ip = self.selected_bridge.ip_address
        self.client.username = ""
        self.persist_config()
        self.pair_poll_attempts_remaining = 30
        self.hub_page.set_pair_button_enabled(False)
        self.set_hub_status("Waiting for the bridge button. Press it now and the app will detect it automatically.")
        self.try_pair_bridge()

    def try_pair_bridge(self) -> None:
        self.run_task(self.client.create_user, self.on_bridge_paired, on_error=self.handle_pair_error)

    def on_bridge_paired(self, username: str) -> None:
        self.pair_poll_timer.stop()
        self.pair_poll_attempts_remaining = 0
        self.client.username = username
        self.persist_config()
        self.hub_page.set_pair_button_enabled(True)
        self.show_home_page()
        self.set_status("Bridge paired successfully. Loading lights...")
        self.refresh_lights()
        self.refresh_hub_steps()

    def handle_pair_error(self, message: str) -> None:
        if "link button not pressed" in message.lower():
            self.pair_poll_attempts_remaining -= 1
            if self.pair_poll_attempts_remaining > 0:
                self.set_hub_status(
                    f"Waiting for bridge button press... {self.pair_poll_attempts_remaining}s remaining."
                )
                self.pair_poll_timer.start(1000)
                return
            self.hub_page.set_pair_button_enabled(True)
            self.set_hub_status("Pairing timed out. Press the bridge button and try Pair Bridge again.")
            return
        self.pair_poll_timer.stop()
        self.pair_poll_attempts_remaining = 0
        self.hub_page.set_pair_button_enabled(True)
        self.handle_task_error(message)

    def forget_hub(self) -> None:
        self.pair_poll_timer.stop()
        self.pair_poll_attempts_remaining = 0
        self.selected_bridge = None
        self.discovered_bridges = []
        self.clear_saved_pairing()
        self.current_lights.clear()
        self.home_page.clear_lights()
        self.show_hub_page()
        self.set_hub_status("Hub removed. Discover a bridge to add it again.")

    def clear_saved_pairing(self) -> None:
        self.client.bridge_ip = ""
        self.client.username = ""
        self.persist_config()

    def refresh_lights(self) -> None:
        if not self.client.is_configured():
            self.show_hub_page()
            self.set_hub_status("Add a hub before loading lights.")
            return
        if self.light_operation_in_flight:
            return
        self.set_status("Refreshing lights...")
        self.refresh_request_token += 1
        request_token = self.refresh_request_token
        self.run_task(
            self.client.list_lights,
            lambda lights, token=request_token: self.render_lights_if_current(token, lights),
            on_error=self.handle_task_error,
        )

    def render_lights_if_current(self, token: int, lights: list[Light]) -> None:
        if token != self.refresh_request_token:
            return
        self.current_lights = {light.light_id: light for light in lights}
        self.home_page.set_lights(lights)
        self.set_controls_enabled(True)
        self.light_operation_in_flight = False
        if lights:
            self.set_status(f"Loaded {len(lights)} light{'s' if len(lights) != 1 else ''}.")
        else:
            self.set_status("No lights available.")

    def set_controls_enabled(self, enabled: bool) -> None:
        self.home_page.set_controls_enabled(enabled)
        self.sidebar.set_controls_enabled(enabled)

    def begin_light_operation(self, status_message: str) -> None:
        self.light_operation_in_flight = True
        self.set_controls_enabled(False)
        self.set_status(status_message)

    def handle_power_toggle(self, light_id: str, is_on: bool) -> None:
        light = self.current_lights.get(light_id)
        if light is None or self.light_operation_in_flight:
            return
        self.begin_light_operation(f"Updating {light.name}...")
        self.run_task(
            lambda: self.client.set_power(light.light_id, is_on),
            lambda _: self.after_light_change(f"{light.name} updated."),
            on_error=self.handle_task_error,
        )

    def set_all_power(self, is_on: bool) -> None:
        if not self.current_lights or self.light_operation_in_flight:
            return
        light_ids = list(self.current_lights.keys())
        self.begin_light_operation(f"Turning all lights {'on' if is_on else 'off'}...")

        def turn_all() -> None:
            for light_id in light_ids:
                self.client.set_power(light_id, is_on)

        self.run_task(
            turn_all,
            lambda _: self.after_light_change(f"All lights turned {'on' if is_on else 'off'}."),
            on_error=self.handle_task_error,
        )

    def change_brightness(self, light_id: str, brightness: int) -> None:
        light = self.current_lights.get(light_id)
        if light is None or self.light_operation_in_flight:
            return
        self.begin_light_operation(f"Setting {light.name} brightness to {brightness}%...")
        self.run_task(
            lambda: self.client.set_brightness(light.light_id, brightness),
            lambda _: self.after_light_change(f"{light.name} brightness updated."),
            on_error=self.handle_task_error,
        )

    def change_temperature(self, light_id: str, mirek: int) -> None:
        light = self.current_lights.get(light_id)
        if light is None or self.light_operation_in_flight:
            return
        kelvin = HueBridgeClient.mirek_to_kelvin(mirek)
        self.begin_light_operation(f"Setting {light.name} temperature to {kelvin}K...")
        self.run_task(
            lambda: self.client.set_color_temperature(light.light_id, mirek),
            lambda _: self.after_light_change(f"{light.name} temperature updated."),
            on_error=self.handle_task_error,
        )

    def handle_color_picked(self, light_id: str, color: QColor) -> None:
        light = self.current_lights.get(light_id)
        if light is None or self.light_operation_in_flight:
            return
        self.begin_light_operation(f"Updating {light.name} color...")
        self.run_task(
            lambda: self.client.set_color_rgb(light.light_id, color.red(), color.green(), color.blue()),
            lambda _: self.after_light_change(f"{light.name} color updated."),
            on_error=self.handle_task_error,
        )

    def after_light_change(self, message: str) -> None:
        self.set_status(message)
        self.refresh_request_token += 1
        request_token = self.refresh_request_token
        self.run_task(
            self.client.list_lights,
            lambda lights, token=request_token: self.render_lights_if_current(token, lights),
            on_error=self.handle_task_error,
        )


def main() -> int:
    app = QApplication(sys.argv)
    app_icon = HueRemoteWindow.app_icon()
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)
    window = HueRemoteWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
