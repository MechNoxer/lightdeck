"""A tiny self-contained line-icon set, rendered from inline SVG via QtSvg.

Icons are defined as plain-text SVG templates with a single ``{c}`` color
placeholder so no binary assets are needed and icons can be tinted on demand.
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
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
}

_cache: dict[tuple[str, str, int], QIcon] = {}


def icon(name: str, color: str = "#f2f0ec", size: int = 20) -> QIcon:
    key = (name, color, size)
    cached = _cache.get(key)
    if cached is not None:
        return cached

    svg = _TEMPLATES[name].replace("{c}", color)
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter)
    painter.end()

    result = QIcon(pixmap)
    _cache[key] = result
    return result
