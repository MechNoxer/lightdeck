"""Design tokens and shared styling helpers for the Hue remote UI."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QWidget


class Color:
    BG = "#121214"
    BG_GRADIENT_EDGE = "#17171a"
    SIDEBAR = "#17171a"
    PANEL = "rgba(27, 27, 30, 0.92)"
    PANEL_BORDER = "rgba(255, 255, 255, 0.06)"
    HAIRLINE = "rgba(255, 255, 255, 0.08)"
    SURFACE_HOVER = "rgba(255, 255, 255, 0.06)"

    TEXT_PRIMARY = "#f2f0ec"
    TEXT_SECONDARY = "#a8a5a0"
    TEXT_MUTED = "#726f6a"

    ACCENT = "#f39a23"
    ACCENT_LIGHT = "#ffac43"
    ACCENT_SOFT = "rgba(243, 154, 35, 0.16)"
    ACCENT_BORDER = "rgba(243, 154, 35, 0.35)"

    SUCCESS = "#70c18d"
    DANGER = "#d46b5f"

    WARM = "#ffb46b"
    COOL = "#8fc7ff"


class Spacing:
    XS = 4
    SM = 8
    MD = 12
    LG = 16
    XL = 20
    XXL = 24
    XXXL = 32


class Type:
    PAGE_TITLE = 32
    PANEL_TITLE = 20
    CARD_TITLE = 16
    BODY = 14
    SMALL = 13
    KICKER = 11


PRESET_COLORS: list[tuple[str, str]] = [
    ("Warm White", "#ffd9a8"),
    ("Cool White", "#dce9ff"),
    ("Red", "#ff5a4e"),
    ("Orange", "#ff9d3d"),
    ("Yellow", "#ffd23d"),
    ("Green", "#5ed88a"),
    ("Blue", "#4e8dff"),
    ("Purple", "#b06bff"),
]


def apply_elevation(widget: QWidget, *, blur: float = 28, y_offset: float = 8, alpha: int = 120) -> None:
    """Give a panel/card a soft drop shadow that QSS alone can't produce."""
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur)
    shadow.setOffset(0, y_offset)
    shadow.setColor(QColor(0, 0, 0, alpha))
    widget.setGraphicsEffect(shadow)


def rounded_pixmap(source: QPixmap, size: int) -> QPixmap:
    """Return a circular crop of ``source`` scaled to ``size``x``size``."""
    scaled = source.scaled(
        size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
    )
    result = QPixmap(size, size)
    result.fill(Qt.transparent)

    painter = QPainter(result)
    painter.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addEllipse(0, 0, size, size)
    painter.setClipPath(path)
    x = (size - scaled.width()) // 2
    y = (size - scaled.height()) // 2
    painter.drawPixmap(x, y, scaled)
    painter.end()
    return result


def build_stylesheet() -> str:
    return f"""
    QWidget {{ color: {Color.TEXT_PRIMARY}; }}
    QMainWindow {{
        background:
            qradialgradient(cx: 0.98, cy: 0.02, radius: 0.35, fx: 0.98, fy: 0.02,
            stop: 0 rgba(243, 154, 35, 0.14), stop: 1 rgba(0, 0, 0, 0)),
            qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1,
            stop: 0 #0f0f10, stop: 0.5 {Color.BG}, stop: 1 #101011);
    }}

    QFrame#Sidebar {{
        background: {Color.SIDEBAR};
        border-right: 1px solid {Color.HAIRLINE};
    }}
    QLabel#BrandTitle {{ font-size: 16px; font-weight: 700; }}

    QLabel#RailKicker, QLabel#WorkspaceKicker, QLabel#SurfaceKicker {{
        color: {Color.ACCENT};
        font-size: {Type.KICKER}px;
        font-weight: 600;
    }}
    QLabel#SidebarSummary, QLabel#MetaBlock {{
        color: {Color.TEXT_SECONDARY};
        background: rgba(255, 255, 255, 0.04);
        border: 1px solid {Color.HAIRLINE};
        border-radius: 14px;
        padding: 12px 14px;
        font-size: {Type.SMALL}px;
    }}

    QLabel#WorkspaceTitle {{ font-size: {Type.PAGE_TITLE}px; font-weight: 700; }}
    QLabel#WorkspaceCopy, QLabel#HeroSubtitle {{
        color: {Color.TEXT_SECONDARY};
        font-size: {Type.BODY}px;
    }}
    QLabel#PanelTitle {{ font-size: {Type.PANEL_TITLE}px; font-weight: 700; }}
    QLabel#CardTitle {{ font-size: {Type.CARD_TITLE}px; font-weight: 600; }}
    QLabel#CardMeta {{ color: {Color.TEXT_SECONDARY}; font-size: 12px; }}
    QLabel#SectionLabel {{ color: {Color.TEXT_SECONDARY}; font-size: 12px; font-weight: 600; }}
    QLabel#ValueLabel {{ font-size: {Type.SMALL}px; font-weight: 700; }}

    QLabel#MetaPill, QLabel#StatusPill {{
        background: rgba(255, 255, 255, 0.07);
        border: 1px solid {Color.HAIRLINE};
        border-radius: 16px;
        padding: 8px 14px;
        font-size: {Type.SMALL}px;
    }}

    QFrame[panel="true"] {{
        background: {Color.PANEL};
        border: 1px solid {Color.PANEL_BORDER};
        border-radius: 20px;
    }}
    QFrame[card="true"] {{
        background: {Color.PANEL};
        border: 1px solid {Color.PANEL_BORDER};
        border-radius: 18px;
    }}
    QFrame[card="true"][unreachable="true"] {{
        border: 1px solid rgba(212, 107, 95, 0.35);
    }}

    QPushButton#NavButton {{
        text-align: left;
        padding: 12px 14px;
        border-radius: 14px;
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid transparent;
        color: {Color.TEXT_PRIMARY};
        font-weight: 600;
    }}
    QPushButton#NavButton:checked {{
        background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
            stop: 0 rgba(243, 154, 35, 0.16), stop: 1 rgba(243, 154, 35, 0.05));
        border: 1px solid {Color.ACCENT_BORDER};
    }}
    QPushButton#GhostButton, QPushButton#SecondaryButton {{
        padding: 10px 14px;
        background: rgba(255, 255, 255, 0.06);
        color: {Color.TEXT_PRIMARY};
        border-radius: 12px;
        border: 1px solid {Color.HAIRLINE};
        font-weight: 600;
    }}
    QPushButton#AccentButton {{
        padding: 10px 16px;
        background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1,
            stop: 0 {Color.ACCENT}, stop: 1 {Color.ACCENT_LIGHT});
        color: #181818;
        border-radius: 12px;
        border: none;
        font-weight: 700;
    }}
    QPushButton#PresetSwatch {{
        border-radius: 12px;
        border: 1px solid {Color.HAIRLINE};
    }}
    QPushButton#ModeTab {{
        padding: 6px 16px;
        border-radius: 10px;
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid transparent;
        color: {Color.TEXT_SECONDARY};
        font-size: 12px;
        font-weight: 600;
    }}
    QPushButton#ModeTab:checked {{
        background: {Color.ACCENT_SOFT};
        border: 1px solid {Color.ACCENT_BORDER};
        color: {Color.TEXT_PRIMARY};
    }}
    QPushButton:disabled {{ color: {Color.TEXT_MUTED}; }}
    QPushButton:hover {{ border-color: {Color.ACCENT_BORDER}; }}

    QComboBox, QLineEdit {{
        min-height: 40px;
        padding: 0 12px;
        border-radius: 12px;
        background: rgba(255, 255, 255, 0.06);
        border: 1px solid {Color.HAIRLINE};
        font-size: {Type.BODY}px;
    }}
    QLineEdit#SearchField {{ min-height: 42px; }}

    QScrollArea#CardsScrollArea, QScrollArea#CardsScrollArea > QWidget > QWidget {{
        background: transparent;
        border: none;
    }}
    QWidget#CardsContainer {{ background: transparent; }}
    QScrollArea#CardsScrollArea QScrollBar:vertical {{
        width: 10px;
        background: transparent;
        margin: 0;
    }}
    QScrollArea#CardsScrollArea QScrollBar::handle:vertical {{
        background: rgba(255, 255, 255, 0.14);
        border-radius: 5px;
        min-height: 32px;
    }}
    QScrollArea#CardsScrollArea QScrollBar::handle:vertical:hover {{
        background: rgba(255, 255, 255, 0.24);
    }}
    QScrollArea#CardsScrollArea QScrollBar::add-line:vertical,
    QScrollArea#CardsScrollArea QScrollBar::sub-line:vertical {{
        height: 0;
    }}

    QSlider::groove:horizontal {{
        border-radius: 4px;
        height: 8px;
        background: rgba(255, 255, 255, 0.10);
    }}
    QSlider#BrightnessSlider::sub-page:horizontal {{
        border-radius: 4px;
        background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 0,
            stop: 0 {Color.ACCENT}, stop: 1 {Color.ACCENT_LIGHT});
    }}
    QSlider#TemperatureSlider::groove:horizontal {{
        border-radius: 4px;
        height: 8px;
        background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 0,
            stop: 0 {Color.WARM}, stop: 1 {Color.COOL});
    }}
    QSlider::handle:horizontal {{
        width: 16px;
        margin: -5px 0;
        border-radius: 8px;
        background: #ffffff;
        border: 2px solid #181818;
    }}

    QLabel#StepChip {{
        border-radius: 14px;
        padding: 8px 14px;
        font-size: 12px;
        font-weight: 600;
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid {Color.HAIRLINE};
        color: {Color.TEXT_SECONDARY};
    }}
    QLabel#StepChip[state="active"] {{
        background: {Color.ACCENT_SOFT};
        border: 1px solid {Color.ACCENT_BORDER};
        color: {Color.TEXT_PRIMARY};
    }}
    QLabel#StepChip[state="done"] {{
        background: rgba(112, 193, 141, 0.14);
        border: 1px solid rgba(112, 193, 141, 0.35);
        color: {Color.TEXT_PRIMARY};
    }}
    QLabel#StepConnector {{ color: {Color.TEXT_MUTED}; }}
    """
