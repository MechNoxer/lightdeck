# PyInstaller spec for Windows, macOS and Linux builds.
# Run from the repository root:  pyinstaller packaging/pyinstaller/lightdeck.spec
# -*- mode: python ; coding: utf-8 -*-

import re
import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parents[1]  # noqa: F821 - provided by PyInstaller
VERSION = re.search(r'__version__ = "([^"]+)"', (ROOT / "src/lightdeck/__init__.py").read_text()).group(1)
ICONS = ROOT / "packaging" / "icons"

# Qt modules the app never touches; leaving them out keeps the bundle small.
EXCLUDES = [
    "tkinter",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuickWidgets",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtMultimedia",
    "PySide6.QtPdf",
]

a = Analysis(  # noqa: F821
    [str(ROOT / "packaging/pyinstaller/entry.py")],
    pathex=[str(ROOT / "src")],
    datas=[(str(ROOT / "src/lightdeck/assets"), "lightdeck/assets")],
    excludes=EXCLUDES,
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821

icon = None
if sys.platform == "win32":
    icon = str(ICONS / "lightdeck.ico")
elif sys.platform == "darwin":
    icon = str(ICONS / "lightdeck.icns")

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Lightdeck" if sys.platform != "linux" else "lightdeck",
    console=False,
    icon=icon,
    upx=False,
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    name="Lightdeck" if sys.platform != "linux" else "lightdeck",
    upx=False,
)

if sys.platform == "darwin":
    app = BUNDLE(  # noqa: F821
        coll,
        name="Lightdeck.app",
        icon=icon,
        bundle_identifier="io.github.mechnoxer.lightdeck",
        version=VERSION,
        info_plist={
            "CFBundleDisplayName": "Lightdeck",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "LSApplicationCategoryType": "public.app-category.utilities",
            "NSHighResolutionCapable": True,
            "NSRequiresAquaSystemAppearance": False,
            # macOS asks the user before an app may talk to devices on the LAN.
            "NSLocalNetworkUsageDescription": "Lightdeck connects to your Hue Bridge on your local network.",
            "NSBonjourServices": ["_hue._tcp"],
        },
    )
