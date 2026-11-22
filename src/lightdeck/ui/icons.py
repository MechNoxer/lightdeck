"""A tiny self-contained line-icon set, rendered from inline SVG via QtSvg.

Icons are defined as plain-text SVG templates with a single ``{c}`` color
placeholder so no binary assets are needed and icons can be tinted on demand.
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_STROKE = 'fill="none" stroke="{c}" stroke-width="{w}" stroke-linecap="round" stroke-linejoin="round"'

_TEMPLATES: dict[str, str] = {
    "bulb": f"""
        <svg viewBox="0 0 24 24" {_STROKE.format(c="{c}", w=1.8)}>
            <path d="M9 21h6"/>
            <path d="M10 18h4"/>
            <path d="M12 2a7 7 0 0 0-4 12.7c.7.5 1 1.2 1 2.3h6c0-1.1.3-1.8 1-2.3A7 7 0 0 0 12 2z"/>
        </svg>
    """,
    "power": f"""
        <svg viewBox="0 0 24 24" {_STROKE.format(c="{c}", w=2)}>
            <line x1="12" y1="2" x2="12" y2="11"/>
            <path d="M6 5.5a9 9 0 1 0 12 0"/>
        </svg>
    """,
    "refresh": f"""
        <svg viewBox="0 0 24 24" {_STROKE.format(c="{c}", w=2)}>
            <path d="M20 6v5h-5"/>
            <path d="M4 18v-5h5"/>
            <path d="M5.6 9A7.5 7.5 0 0 1 19 8.5M18.4 15A7.5 7.5 0 0 1 5 15.5"/>
        </svg>
    """,
    "plus": f"""
        <svg viewBox="0 0 24 24" {_STROKE.format(c="{c}", w=2)}>
            <line x1="12" y1="4" x2="12" y2="20"/>
            <line x1="4" y1="12" x2="20" y2="12"/>
        </svg>
    """,
    "unlink": f"""
        <svg viewBox="0 0 24 24" {_STROKE.format(c="{c}", w=2)}>
            <path d="M14 7l1-1a3.5 3.5 0 0 1 5 5l-1 1"/>
            <path d="M10 17l-1 1a3.5 3.5 0 0 1-5-5l1-1"/>
            <line x1="9" y1="15" x2="10.5" y2="13.5"/>
            <line x1="13.5" y1="10.5" x2="15" y2="9"/>
        </svg>
    """,
    "search": f"""
        <svg viewBox="0 0 24 24" {_STROKE.format(c="{c}", w=2)}>
            <circle cx="11" cy="11" r="6.5"/>
            <line x1="20" y1="20" x2="15.8" y2="15.8"/>
        </svg>
    """,
    "sun": f"""
        <svg viewBox="0 0 24 24" {_STROKE.format(c="{c}", w=2)}>
            <circle cx="12" cy="12" r="4"/>
            <line x1="12" y1="2" x2="12" y2="4.5"/>
            <line x1="12" y1="19.5" x2="12" y2="22"/>
            <line x1="2" y1="12" x2="4.5" y2="12"/>
            <line x1="19.5" y1="12" x2="22" y2="12"/>
            <line x1="4.9" y1="4.9" x2="6.6" y2="6.6"/>
            <line x1="17.4" y1="17.4" x2="19.1" y2="19.1"/>
            <line x1="4.9" y1="19.1" x2="6.6" y2="17.4"/>
            <line x1="17.4" y1="6.6" x2="19.1" y2="4.9"/>
        </svg>
    """,
    "thermometer": f"""
        <svg viewBox="0 0 24 24" {_STROKE.format(c="{c}", w=2)}>
            <path d="M12 14.5V4a2 2 0 1 0-4 0v10.5a4 4 0 1 0 4 0z"/>
        </svg>
    """,
    "palette": f"""
        <svg viewBox="0 0 24 24" {_STROKE.format(c="{c}", w=1.8)}>
            <path d="M12 3a9 9 0 1 0 0 18h1.5a2 2 0 0 0 1.4-3.4 1.6 1.6 0 0 1 1.1-2.7H18a3 3 0 0 0 3-3c0-5-4-8.9-9-8.9z"/>
            <circle cx="7.5" cy="10.5" r="1.1" fill="{{c}}" stroke="none"/>
            <circle cx="11" cy="7" r="1.1" fill="{{c}}" stroke="none"/>
            <circle cx="15.5" cy="8" r="1.1" fill="{{c}}" stroke="none"/>
        </svg>
    """,
    "chevron-left": f"""
        <svg viewBox="0 0 24 24" {_STROKE.format(c="{c}", w=2)}>
            <polyline points="15 5 8 12 15 19"/>
        </svg>
    """,
    "router": f"""
        <svg viewBox="0 0 24 24" {_STROKE.format(c="{c}", w=2)}>
            <rect x="3" y="10" width="18" height="7" rx="2"/>
            <line x1="7" y1="13.5" x2="7.01" y2="13.5"/>
            <line x1="11" y1="13.5" x2="11.01" y2="13.5"/>
            <path d="M8 10V7a4 4 0 0 1 8 0v3"/>
        </svg>
    """,
    "check": f"""
        <svg viewBox="0 0 24 24" {_STROKE.format(c="{c}", w=2.2)}>
            <polyline points="5 13 10 18 19 7"/>
        </svg>
    """,
    "home": f"""
        <svg viewBox="0 0 24 24" {_STROKE.format(c="{c}", w=2)}>
            <path d="M3 10.5 12 3l9 7.5"/>
            <path d="M5 9v11h14V9"/>
            <path d="M10 20v-6h4v6"/>
        </svg>
    """,
    "settings": f"""
        <svg viewBox="0 0 24 24" {_STROKE.format(c="{c}", w=2)}>
            <circle cx="12" cy="12" r="3"/>
            <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>
        </svg>
    """,
    "close": f"""
        <svg viewBox="0 0 24 24" {_STROKE.format(c="{c}", w=2)}>
            <line x1="6" y1="6" x2="18" y2="18"/>
            <line x1="18" y1="6" x2="6" y2="18"/>
        </svg>
    """,
    "more": """
        <svg viewBox="0 0 24 24" fill="{c}">
            <circle cx="5" cy="12" r="1.8"/><circle cx="12" cy="12" r="1.8"/><circle cx="19" cy="12" r="1.8"/>
        </svg>
    """,
    "edit": f"""
        <svg viewBox="0 0 24 24" {_STROKE.format(c="{c}", w=2)}>
            <path d="M4 20h4L19 9a2.8 2.8 0 0 0-4-4L4 16z"/>
            <line x1="13.5" y1="6.5" x2="17.5" y2="10.5"/>
        </svg>
    """,
    "trash": f"""
        <svg viewBox="0 0 24 24" {_STROKE.format(c="{c}", w=2)}>
            <polyline points="4 7 20 7"/>
            <path d="M6 7l1 13h10l1-13"/>
            <path d="M9 7V4h6v3"/>
        </svg>
    """,
    "room": f"""
        <svg viewBox="0 0 24 24" {_STROKE.format(c="{c}", w=2)}>
            <path d="M5 21V4a1 1 0 0 1 1-1h12a1 1 0 0 1 1 1v17"/>
            <line x1="3" y1="21" x2="21" y2="21"/>
            <line x1="14.5" y1="12" x2="14.5" y2="12.5"/>
        </svg>
    """,
    "zone": f"""
        <svg viewBox="0 0 24 24" {_STROKE.format(c="{c}", w=2)}>
            <polygon points="12 3 21 8 12 13 3 8 12 3"/>
            <polyline points="3 13 12 18 21 13"/>
        </svg>
    """,
    "sparkles": f"""
        <svg viewBox="0 0 24 24" {_STROKE.format(c="{c}", w=1.8)}>
            <path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/>
            <path d="M19 15l.7 2 2 .7-2 .7-.7 2-.7-2-2-.7 2-.7z"/>
        </svg>
    """,
    "wifi-off": f"""
        <svg viewBox="0 0 24 24" {_STROKE.format(c="{c}", w=2)}>
            <line x1="3" y1="3" x2="21" y2="21"/>
            <path d="M8.5 16.5a5 5 0 0 1 7 0"/>
            <path d="M5 13a10 10 0 0 1 5.5-2.8M19 13a10 10 0 0 0-2.4-1.7"/>
            <line x1="12" y1="20" x2="12.01" y2="20"/>
        </svg>
    """,
    "moon": f"""
        <svg viewBox="0 0 24 24" {_STROKE.format(c="{c}", w=2)}>
            <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>
        </svg>
    """,
}

_cache: dict[tuple[str, str, int, float], QIcon] = {}


def _device_pixel_ratio() -> float:
    app = QGuiApplication.instance()
    screen = app.primaryScreen() if app else None
    return max(1.0, screen.devicePixelRatio()) if screen else 1.0


def pixmap(name: str, color: str, size: int = 20) -> QPixmap:
    dpr = _device_pixel_ratio()
    svg = _TEMPLATES[name].replace("{c}", color)
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    result = QPixmap(round(size * dpr), round(size * dpr))
    result.fill(Qt.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter)
    painter.end()
    result.setDevicePixelRatio(dpr)
    return result


def icon(name: str, color: str = "#f2f0ec", size: int = 20) -> QIcon:
    key = (name, color, size, _device_pixel_ratio())
    cached = _cache.get(key)
    if cached is None:
        cached = _cache[key] = QIcon(pixmap(name, color, size))
    return cached
