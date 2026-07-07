"""Top-level screens: the device sidebar, the lights home page, and the add-hub page."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .hue_api import Bridge, Light
from .icons import icon
from .theme import Spacing, apply_elevation, rounded_pixmap
from .widgets import LightCard

_ASSET_ICON_PATH = Path(__file__).resolve().parent / "assets" / "philips-hue-for-arch.png"


def _brand_avatar_pixmap(size: int = 52) -> QPixmap:
    if _ASSET_ICON_PATH.exists():
        source = QPixmap(str(_ASSET_ICON_PATH))
        if not source.isNull():
            return rounded_pixmap(source, size)

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor("#ece8e1"))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(0, 0, size, size)
    painter.setPen(QColor("#181818"))
    font = QFont()
    font.setPointSize(size // 3)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "H")
    painter.end()
    return pixmap


def _icon_button(text: str, icon_name: str, object_name: str) -> QPushButton:
    button = QPushButton(f"  {text}")
    button.setObjectName(object_name)
    icon_color = "#181818" if object_name == "AccentButton" else "#f2f0ec"
    button.setIcon(icon(icon_name, icon_color, 16))
    button.setIconSize(QSize(16, 16))
    return button


class Sidebar(QFrame):
    lightsRequested = Signal()
    addHubRequested = Signal()
    refreshRequested = Signal()
    forgetRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setMinimumWidth(220)
        self.setMaximumWidth(250)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.XL, Spacing.XXL, Spacing.XL, Spacing.XXL)
        layout.setSpacing(Spacing.XXL)

        brand_row = QHBoxLayout()
        brand_row.setSpacing(Spacing.MD)
        avatar = QLabel()
        avatar.setPixmap(_brand_avatar_pixmap())
        avatar.setFixedSize(52, 52)

        brand_copy = QVBoxLayout()
        brand_copy.setSpacing(2)
        kicker = QLabel("Connected")
        kicker.setObjectName("RailKicker")
        title = QLabel("Devices")
        title.setObjectName("BrandTitle")
        brand_copy.addWidget(kicker)
        brand_copy.addWidget(title)

        brand_row.addWidget(avatar)
        brand_row.addLayout(brand_copy, 1)

        self.summary_label = QLabel("No Hue bridge paired yet.")
        self.summary_label.setObjectName("SidebarSummary")
        self.summary_label.setWordWrap(True)

        self.lights_button = QPushButton("  Lights")
        self.lights_button.setObjectName("NavButton")
        self.lights_button.setIcon(icon("bulb", "#f2f0ec", 18))
        self.lights_button.setIconSize(QSize(18, 18))
        self.lights_button.setCheckable(True)
        self.lights_button.clicked.connect(self.lightsRequested)

        self.add_hub_button = QPushButton("  Add Hub")
        self.add_hub_button.setObjectName("NavButton")
        self.add_hub_button.setIcon(icon("plus", "#f2f0ec", 18))
        self.add_hub_button.setIconSize(QSize(18, 18))
        self.add_hub_button.setCheckable(True)
        self.add_hub_button.clicked.connect(self.addHubRequested)

        nav_stack = QVBoxLayout()
        nav_stack.setSpacing(Spacing.SM)
        nav_stack.addWidget(self.lights_button)
        nav_stack.addWidget(self.add_hub_button)

        self.refresh_button = QPushButton("  Refresh Lights")
        self.refresh_button.setObjectName("GhostButton")
        self.refresh_button.setIcon(icon("refresh", "#f2f0ec", 16))
        self.refresh_button.setIconSize(QSize(16, 16))
        self.refresh_button.clicked.connect(self.refreshRequested)

        self.forget_button = QPushButton("  Forget Hub")
        self.forget_button.setObjectName("GhostButton")
        self.forget_button.setIcon(icon("unlink", "#f2f0ec", 16))
        self.forget_button.setIconSize(QSize(16, 16))
        self.forget_button.clicked.connect(self.forgetRequested)

        footer = QVBoxLayout()
        footer.setSpacing(Spacing.SM)
        footer.addWidget(self.refresh_button)
        footer.addWidget(self.forget_button)

        layout.addLayout(brand_row)
        layout.addWidget(self.summary_label)
        layout.addLayout(nav_stack)
        layout.addStretch(1)
        layout.addLayout(footer)

    def set_summary(self, text: str) -> None:
        self.summary_label.setText(text)

    def set_active(self, lights_active: bool) -> None:
        self.lights_button.setChecked(lights_active)
        self.add_hub_button.setChecked(not lights_active)

    def set_controls_enabled(self, enabled: bool) -> None:
        self.refresh_button.setEnabled(enabled)
        self.forget_button.setEnabled(enabled)


class HomePage(QWidget):
    refreshRequested = Signal()
    addHubRequested = Signal()
    forgetRequested = Signal()
    allOnRequested = Signal()
    allOffRequested = Signal()
    lightPowerToggled = Signal(str, bool)
    lightBrightnessChanged = Signal(str, int)
    lightTemperatureChanged = Signal(str, int)
    lightColorPicked = Signal(str, QColor)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._lights: dict[str, Light] = {}
        self._cards: dict[str, LightCard] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.XXL, Spacing.XXL, Spacing.XXL, Spacing.XL)
        layout.setSpacing(Spacing.LG)

        header = QFrame()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(Spacing.LG)

        title_stack = QVBoxLayout()
        title_stack.setSpacing(4)
        kicker = QLabel("Lighting Studio")
        kicker.setObjectName("WorkspaceKicker")
        title = QLabel("Philips Hue Control")
        title.setObjectName("WorkspaceTitle")
        title.setWordWrap(True)
        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("WorkspaceCopy")
        self.status_label.setWordWrap(True)
        title_stack.addWidget(kicker)
        title_stack.addWidget(title)
        title_stack.addWidget(self.status_label)

        badge_col = QVBoxLayout()
        badge_col.setSpacing(Spacing.SM)
        self.bridge_badge = QLabel("No hub")
        self.bridge_badge.setObjectName("MetaPill")
        self.light_count_badge = QLabel("0 lights")
        self.light_count_badge.setObjectName("StatusPill")
        badge_col.addWidget(self.bridge_badge, 0, Qt.AlignRight)
        badge_col.addWidget(self.light_count_badge, 0, Qt.AlignRight)

        header_layout.addLayout(title_stack, 1)
        header_layout.addLayout(badge_col)

        overview_panel = QFrame()
        overview_panel.setProperty("panel", True)
        apply_elevation(overview_panel)
        overview_layout = QVBoxLayout(overview_panel)
        overview_layout.setContentsMargins(Spacing.XXL, Spacing.XXL, Spacing.XXL, Spacing.XXL)
        overview_layout.setSpacing(Spacing.MD)

        overview_kicker = QLabel("Bridge Overview")
        overview_kicker.setObjectName("SurfaceKicker")
        overview_title = QLabel("All lights")
        overview_title.setObjectName("PanelTitle")

        self.home_meta = QLabel("No Hue bridge paired.")
        self.home_meta.setObjectName("MetaBlock")
        self.home_meta.setWordWrap(True)

        top_controls = QHBoxLayout()
        top_controls.setSpacing(Spacing.SM)
        self.add_hub_button = _icon_button("Add Hub", "plus", "SecondaryButton")
        self.add_hub_button.clicked.connect(self.addHubRequested)
        self.refresh_button = _icon_button("Refresh", "refresh", "AccentButton")
        self.refresh_button.clicked.connect(self.refreshRequested)
        self.forget_button = _icon_button("Forget", "unlink", "SecondaryButton")
        self.forget_button.clicked.connect(self.forgetRequested)

        top_controls.addStretch(1)
        top_controls.addWidget(self.add_hub_button)
        top_controls.addWidget(self.refresh_button)
        top_controls.addWidget(self.forget_button)

        overview_layout.addWidget(overview_kicker)
        overview_layout.addWidget(overview_title)
        overview_layout.addWidget(self.home_meta)
        overview_layout.addLayout(top_controls)

        control_panel = QFrame()
        control_panel.setProperty("panel", True)
        apply_elevation(control_panel)
        control_layout = QVBoxLayout(control_panel)
        control_layout.setContentsMargins(Spacing.XXL, Spacing.XXL, Spacing.XXL, Spacing.XXL)
        control_layout.setSpacing(Spacing.MD)

        lights_kicker = QLabel("Lighting Board")
        lights_kicker.setObjectName("SurfaceKicker")
        lights_title = QLabel("Every light visible")
        lights_title.setObjectName("PanelTitle")

        toolbar = QHBoxLayout()
        toolbar.setSpacing(Spacing.SM)
        self.search_field = QLineEdit()
        self.search_field.setObjectName("SearchField")
        self.search_field.setPlaceholderText("Search lights...")
        self.search_field.addAction(icon("search", "#a8a5a0", 15), QLineEdit.LeadingPosition)
        self.search_field.textChanged.connect(self._apply_filter)

        self.all_on_button = _icon_button("All On", "power", "GhostButton")
        self.all_on_button.clicked.connect(self.allOnRequested)
        self.all_off_button = _icon_button("All Off", "power", "GhostButton")
        self.all_off_button.clicked.connect(self.allOffRequested)

        toolbar.addWidget(self.search_field, 1)
        toolbar.addWidget(self.all_on_button)
        toolbar.addWidget(self.all_off_button)

        self.empty_lights_label = QLabel("No lights loaded yet.")
        self.empty_lights_label.setObjectName("WorkspaceCopy")
        self.empty_lights_label.setWordWrap(True)

        self.no_results_label = QLabel("No lights match your search.")
        self.no_results_label.setObjectName("WorkspaceCopy")
        self.no_results_label.setWordWrap(True)
        self.no_results_label.setVisible(False)

        cards_container = QWidget()
        cards_container.setObjectName("CardsContainer")
        self.cards_layout = QGridLayout(cards_container)
        self.cards_layout.setContentsMargins(0, 0, Spacing.SM, 0)
        self.cards_layout.setHorizontalSpacing(Spacing.MD)
        self.cards_layout.setVerticalSpacing(Spacing.MD)

        cards_scroll = QScrollArea()
        cards_scroll.setObjectName("CardsScrollArea")
        cards_scroll.setWidgetResizable(True)
        cards_scroll.setFrameShape(QFrame.NoFrame)
        cards_scroll.setWidget(cards_container)

        control_layout.addWidget(lights_kicker)
        control_layout.addWidget(lights_title)
        control_layout.addLayout(toolbar)
        control_layout.addWidget(self.empty_lights_label)
        control_layout.addWidget(self.no_results_label)
        control_layout.addWidget(cards_scroll, 1)

        layout.addWidget(header)
        layout.addWidget(overview_panel)
        layout.addWidget(control_panel, 1)

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def set_bridge_badge(self, text: str) -> None:
        self.bridge_badge.setText(text)

    def set_home_meta(self, text: str) -> None:
        self.home_meta.setText(text)

    def set_light_count(self, count: int) -> None:
        self.light_count_badge.setText(f"{count} light{'s' if count != 1 else ''}")

    def get_light(self, light_id: str) -> Light | None:
        return self._lights.get(light_id)

    def set_controls_enabled(self, enabled: bool) -> None:
        for widget in (
            self.refresh_button,
            self.add_hub_button,
            self.forget_button,
            self.search_field,
            self.all_on_button,
            self.all_off_button,
        ):
            widget.setEnabled(enabled)
        for card in self._cards.values():
            card.setEnabled(enabled)

    def set_lights(self, lights: list[Light]) -> None:
        self._lights = {light.light_id: light for light in lights}
        self.set_light_count(len(lights))
        self._rebuild_grid()

    def clear_lights(self) -> None:
        self._lights = {}
        self.set_light_count(0)
        self._rebuild_grid()

    def _apply_filter(self, _text: str) -> None:
        self._rebuild_grid()

    def _rebuild_grid(self) -> None:
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._cards.clear()

        query = self.search_field.text().strip().lower()
        all_lights = list(self._lights.values())
        visible = sorted(
            (light for light in all_lights if query in light.name.lower()),
            key=lambda light: light.name.lower(),
        )

        self.empty_lights_label.setVisible(not all_lights)
        self.no_results_label.setVisible(bool(all_lights) and bool(query) and not visible)
        if not visible:
            return

        columns = 4 if len(visible) >= 4 else max(1, len(visible))
        for index, light in enumerate(visible):
            card = self._build_card(light)
            self.cards_layout.addWidget(card, index // columns, index % columns)

    def _build_card(self, light: Light) -> LightCard:
        card = LightCard(light)
        card.powerToggled.connect(self.lightPowerToggled)
        card.brightnessChanged.connect(self.lightBrightnessChanged)
        card.temperatureChanged.connect(self.lightTemperatureChanged)
        card.colorPicked.connect(self.lightColorPicked)
        self._cards[light.light_id] = card
        return card


def _step_chip(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("StepChip")
    label.setProperty("state", "pending")
    return label


class HubPage(QWidget):
    discoverRequested = Signal()
    pairRequested = Signal()
    backRequested = Signal()
    bridgeSelected = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.XXL, Spacing.XXL, Spacing.XXL, Spacing.XL)
        layout.setSpacing(Spacing.LG)

        header = QFrame()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(Spacing.LG)

        title_stack = QVBoxLayout()
        title_stack.setSpacing(4)
        kicker = QLabel("Bridge Setup")
        kicker.setObjectName("WorkspaceKicker")
        title = QLabel("Add Hub")
        title.setObjectName("WorkspaceTitle")
        title.setWordWrap(True)
        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("WorkspaceCopy")
        self.status_label.setWordWrap(True)
        title_stack.addWidget(kicker)
        title_stack.addWidget(title)
        title_stack.addWidget(self.status_label)

        self.discovery_badge = QLabel("Waiting")
        self.discovery_badge.setObjectName("MetaPill")

        header_layout.addLayout(title_stack, 1)
        header_layout.addWidget(self.discovery_badge, 0, Qt.AlignTop)

        hub_panel = QFrame()
        hub_panel.setProperty("panel", True)
        apply_elevation(hub_panel)
        panel_layout = QVBoxLayout(hub_panel)
        panel_layout.setContentsMargins(Spacing.XXL, Spacing.XXL, Spacing.XXL, Spacing.XXL)
        panel_layout.setSpacing(Spacing.LG)

        subtitle = QLabel(
            "Discover your Philips Hue Bridge on the network, select it, then pair with the physical bridge button."
        )
        subtitle.setWordWrap(True)
        subtitle.setObjectName("HeroSubtitle")

        step_row = QHBoxLayout()
        step_row.setSpacing(Spacing.SM)
        self.step_discover = _step_chip("1  Discover")
        self.step_select = _step_chip("2  Select")
        self.step_pair = _step_chip("3  Pair")
        connector_1 = QLabel("—")
        connector_1.setObjectName("StepConnector")
        connector_2 = QLabel("—")
        connector_2.setObjectName("StepConnector")
        step_row.addWidget(self.step_discover)
        step_row.addWidget(connector_1)
        step_row.addWidget(self.step_select)
        step_row.addWidget(connector_2)
        step_row.addWidget(self.step_pair)
        step_row.addStretch(1)

        self.bridge_selector = QComboBox()
        self.bridge_selector.currentIndexChanged.connect(self.bridgeSelected)
        self.bridge_details = QLabel("No bridge selected yet.")
        self.bridge_details.setObjectName("MetaBlock")
        self.bridge_details.setWordWrap(True)

        actions = QHBoxLayout()
        actions.setSpacing(Spacing.SM)
        self.back_button = QPushButton()
        self.back_button.setObjectName("SecondaryButton")
        self.back_button.setIcon(icon("chevron-left", "#f2f0ec", 16))
        self.back_button.setText("  Back")
        self.back_button.clicked.connect(self.backRequested)
        self.discover_button = _icon_button("Discover Bridge", "router", "SecondaryButton")
        self.discover_button.clicked.connect(self.discoverRequested)
        self.pair_button = QPushButton("  Pair Bridge")
        self.pair_button.setObjectName("AccentButton")
        self.pair_button.setIcon(icon("check", "#181818", 16))
        self.pair_button.clicked.connect(self.pairRequested)
        self.pair_button.setEnabled(False)
        actions.addWidget(self.back_button)
        actions.addStretch(1)
        actions.addWidget(self.discover_button)
        actions.addWidget(self.pair_button)

        panel_layout.addWidget(subtitle)
        panel_layout.addLayout(step_row)
        panel_layout.addWidget(self.bridge_selector)
        panel_layout.addWidget(self.bridge_details)
        panel_layout.addLayout(actions)
        panel_layout.addStretch(1)

        layout.addWidget(header)
        layout.addWidget(hub_panel, 1)

        self.set_step_states("pending", "pending", "pending")

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def set_discovery_badge(self, text: str) -> None:
        self.discovery_badge.setText(text)

    def set_bridge_details(self, text: str) -> None:
        self.bridge_details.setText(text)

    def set_pair_button_enabled(self, enabled: bool) -> None:
        self.pair_button.setEnabled(enabled)

    def populate_bridges(self, bridges: list[Bridge]) -> None:
        self.bridge_selector.clear()
        for bridge in bridges:
            self.bridge_selector.addItem(f"Hue Bridge {bridge.ip_address}", bridge)

    def current_bridge(self) -> Bridge | None:
        data = self.bridge_selector.currentData()
        return data if isinstance(data, Bridge) else None

    def set_step_states(self, discover: str, select: str, pair: str) -> None:
        for chip, state in (
            (self.step_discover, discover),
            (self.step_select, select),
            (self.step_pair, pair),
        ):
            chip.setProperty("state", state)
            style = chip.style()
            style.unpolish(chip)
            style.polish(chip)
