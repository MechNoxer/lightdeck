"""Design tokens, light/dark palettes and the application stylesheet."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication


@dataclass(frozen=True)
class Palette:
    dark: bool
    bg: str
    sidebar: str
    surface: str
    surface_alt: str
    surface_hover: str
    border: str
    text: str
    text_secondary: str
    text_muted: str
    accent: str
    accent_text: str
    accent_soft: str
    danger: str
    success: str
    track: str


DARK = Palette(
    dark=True,
    bg="#0f1013",
    sidebar="#141519",
    surface="#1a1b20",
    surface_alt="#202127",
    surface_hover="#26272e",
    border="#2a2b32",
    text="#f3f3f5",
    text_secondary="#a3a4ad",
    text_muted="#6d6e78",
    accent="#f5a524",
    accent_text="#1d1400",
    accent_soft="rgba(245, 165, 36, 0.14)",
    danger="#f06464",
    success="#3ecf8e",
    track="#2c2d35",
)

LIGHT = Palette(
    dark=False,
    bg="#f4f4f6",
    sidebar="#ebebef",
    surface="#ffffff",
    surface_alt="#f7f7f9",
    surface_hover="#efeff3",
    border="#e2e2e8",
    text="#15161a",
    text_secondary="#5b5c66",
    text_muted="#9a9ba4",
    accent="#e48c06",
    accent_text="#ffffff",
    accent_soft="rgba(228, 140, 6, 0.12)",
    danger="#d63c3c",
    success="#17a46c",
    track="#e3e3e9",
)

RADIUS = 14
_current = DARK


def current() -> Palette:
    return _current


def qcolor(value: str) -> QColor:
    if value.startswith("rgba"):
        r, g, b, a = (float(p) for p in value[5:-1].split(","))
        return QColor(int(r), int(g), int(b), int(a * 255))
    return QColor(value)


class ThemeManager(QObject):
    changed = Signal()

    def __init__(self, app: QApplication, mode: str = "system") -> None:
        super().__init__(app)
        self._app = app
        self._mode = mode
        hints = QGuiApplication.styleHints()
        if hasattr(hints, "colorSchemeChanged"):
            hints.colorSchemeChanged.connect(lambda _scheme: self._mode == "system" and self.apply())

    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str) -> None:
        self._mode = mode
        self.apply()

    def _system_is_dark(self) -> bool:
        hints = QGuiApplication.styleHints()
        if hasattr(hints, "colorScheme"):
            scheme = hints.colorScheme()
            if scheme == Qt.ColorScheme.Light:
                return False
            if scheme == Qt.ColorScheme.Dark:
                return True
        return True  # unknown: a lighting app reads best dark

    def apply(self) -> None:
        global _current
        dark = self._mode == "dark" or (self._mode == "system" and self._system_is_dark())
        _current = DARK if dark else LIGHT
        p = _current

        palette = QPalette()
        for role, value in (
            (QPalette.Window, p.bg), (QPalette.WindowText, p.text), (QPalette.Base, p.surface),
            (QPalette.AlternateBase, p.surface_alt), (QPalette.Text, p.text), (QPalette.Button, p.surface_alt),
            (QPalette.ButtonText, p.text), (QPalette.Highlight, p.accent), (QPalette.HighlightedText, p.accent_text),
            (QPalette.ToolTipBase, p.surface_alt), (QPalette.ToolTipText, p.text), (QPalette.PlaceholderText, p.text_muted),
        ):
            palette.setColor(role, qcolor(value))
        self._app.setPalette(palette)
        self._app.setStyleSheet(stylesheet(p))
        for widget in self._app.allWidgets():
            widget.update()
        self.changed.emit()


def stylesheet(p: Palette) -> str:
    return f"""
    QWidget {{ color: {p.text}; font-size: 13px; }}
    QMainWindow, QDialog, #AppRoot {{ background: {p.bg}; }}
    QToolTip {{ background: {p.surface_alt}; color: {p.text}; border: 1px solid {p.border};
               border-radius: 6px; padding: 4px 8px; }}

    #Sidebar {{ background: {p.sidebar}; border-right: 1px solid {p.border}; }}
    #BrandName {{ font-size: 16px; font-weight: 700; }}
    #NavSection {{ color: {p.text_muted}; font-size: 11px; font-weight: 700;
                   letter-spacing: 1px; padding: 14px 12px 4px 12px; }}
    #StatusText {{ color: {p.text_secondary}; font-size: 12px; }}

    #PageTitle {{ font-size: 26px; font-weight: 700; }}
    #PageSubtitle {{ color: {p.text_secondary}; font-size: 13px; }}
    #SectionTitle {{ font-size: 15px; font-weight: 650; }}
    #Muted {{ color: {p.text_secondary}; }}
    #Hint {{ color: {p.text_muted}; font-size: 12px; }}
    #CardTitle {{ font-size: 14px; font-weight: 600; }}
    #CardMeta {{ color: {p.text_secondary}; font-size: 12px; }}
    #CardMeta[warn="true"] {{ color: {p.danger}; }}
    #PanelTitle {{ font-size: 18px; font-weight: 700; }}
    #FieldLabel {{ color: {p.text_secondary}; font-size: 12px; font-weight: 600; }}
    #Badge {{ background: {p.accent_soft}; color: {p.accent}; border-radius: 9px;
              padding: 2px 8px; font-size: 11px; font-weight: 700; }}

    #Panel {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: {RADIUS}px; }}
    #Drawer {{ background: {p.surface}; border-left: 1px solid {p.border}; }}

    QPushButton {{ background: {p.surface_alt}; border: 1px solid {p.border}; border-radius: 10px;
                   padding: 8px 14px; font-weight: 600; }}
    QPushButton:hover {{ background: {p.surface_hover}; }}
    QPushButton:pressed {{ background: {p.border}; }}
    QPushButton:disabled {{ color: {p.text_muted}; }}
    QPushButton:focus {{ border-color: {p.accent}; }}
    QPushButton#Primary {{ background: {p.accent}; color: {p.accent_text}; border: none; }}
    QPushButton#Primary:hover {{ background: {p.accent}; border: none; }}
    QPushButton#Primary:disabled {{ background: {p.track}; color: {p.text_muted}; }}
    QPushButton#Ghost {{ background: transparent; border: 1px solid transparent; color: {p.text_secondary}; }}
    QPushButton#Ghost:hover {{ background: {p.surface_hover}; color: {p.text}; }}
    QPushButton#Danger {{ background: transparent; border: 1px solid {p.border}; color: {p.danger}; }}
    QPushButton#Danger:hover {{ background: {p.surface_hover}; }}
    QPushButton#Icon {{ background: transparent; border: none; border-radius: 8px; padding: 6px; }}
    QPushButton#Icon:hover {{ background: {p.surface_hover}; }}
    QPushButton#Segment {{ background: transparent; border: none; border-radius: 8px; padding: 6px 14px;
                           color: {p.text_secondary}; }}
    QPushButton#Segment:checked {{ background: {p.surface}; color: {p.text}; }}
    #SegmentedBar {{ background: {p.track}; border-radius: 10px; }}
    QPushButton#Chip {{ background: {p.surface_alt}; border: 1px solid {p.border}; border-radius: 15px;
                        padding: 5px 12px; font-size: 12px; font-weight: 600; }}
    QPushButton#Chip:hover {{ border-color: {p.text_muted}; }}
    QPushButton#BridgeRow {{ text-align: left; padding: 12px 14px; }}

    QLineEdit {{ background: {p.surface_alt}; border: 1px solid {p.border}; border-radius: 10px;
                 padding: 9px 12px; selection-background-color: {p.accent}; }}
    QLineEdit:focus {{ border-color: {p.accent}; }}

    QCheckBox {{ spacing: 8px; }}
    QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 5px; border: 1.5px solid {p.text_muted};
                            background: transparent; }}
    QCheckBox::indicator:checked {{ background: {p.accent}; border-color: {p.accent}; }}

    QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {p.border}; border-radius: 3px; min-height: 30px; }}
    QScrollBar::handle:vertical:hover {{ background: {p.text_muted}; }}
    QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{
        background: none; height: 0; width: 0; }}

    QMenu {{ background: {p.surface_alt}; border: 1px solid {p.border}; border-radius: 10px; padding: 4px; }}
    QMenu::item {{ padding: 7px 18px 7px 12px; border-radius: 6px; }}
    QMenu::item:selected {{ background: {p.surface_hover}; }}
    """
