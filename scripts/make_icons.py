"""Render the app icon (PNG) and derive .ico / .icns from it.

Usage: python scripts/make_icons.py   (needs PySide6; Pillow for .ico/.icns)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "src" / "lightdeck" / "assets"
PACKAGING = ROOT / "packaging"


def render(size: int = 1024) -> QImage:
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    p = QPainter(image)
    p.setRenderHint(QPainter.Antialiasing)
    s = size / 1024

    # Background tile (macOS-style inset so it sits well next to other icons)
    tile = QRectF(100 * s, 100 * s, 824 * s, 824 * s)
    bg = QLinearGradient(tile.topLeft(), tile.bottomRight())
    bg.setColorAt(0, QColor("#24252d"))
    bg.setColorAt(1, QColor("#0e0f13"))
    path = QPainterPath()
    path.addRoundedRect(tile, 185 * s, 185 * s)
    p.fillPath(path, bg)

    # Three "deck" sliders at different levels and colors
    pills = [
        (300, 0.80, ("#ffb547", "#ff8a3d")),
        (470, 0.58, ("#ff6fa5", "#c86bff")),
        (640, 0.70, ("#4fd1c5", "#4f8dff")),
    ]
    left, width, height = 230 * s, 564 * s, 116 * s
    for top, level, (c1, c2) in pills:
        track = QRectF(left, top * s, width, height)
        track_path = QPainterPath()
        track_path.addRoundedRect(track, height / 2, height / 2)
        p.fillPath(track_path, QColor(255, 255, 255, 26))
        fill = QRectF(left, top * s, height + (width - height) * level, height)
        gradient = QLinearGradient(fill.topLeft(), fill.topRight())
        gradient.setColorAt(0, QColor(c1))
        gradient.setColorAt(1, QColor(c2))
        fill_path = QPainterPath()
        fill_path.addRoundedRect(fill, height / 2, height / 2)
        p.fillPath(fill_path, gradient)
        knob = height * 0.62
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 235))
        p.drawEllipse(QRectF(fill.right() - height / 2 - knob / 2, fill.center().y() - knob / 2, knob, knob))
    p.end()
    return image


def main() -> int:
    QGuiApplication(sys.argv)
    ASSETS.mkdir(parents=True, exist_ok=True)
    png = ASSETS / "lightdeck.png"
    render(512).save(str(png))
    big = PACKAGING / "icons" / "lightdeck-1024.png"
    big.parent.mkdir(parents=True, exist_ok=True)
    render(1024).save(str(big))
    print(f"wrote {png} and {big}")
    try:
        from PIL import Image
    except ImportError:
        print("Pillow not installed; skipping .ico/.icns")
        return 0
    source = Image.open(big)
    source.save(PACKAGING / "icons" / "lightdeck.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    source.save(PACKAGING / "icons" / "lightdeck.icns")
    print("wrote lightdeck.ico and lightdeck.icns")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
