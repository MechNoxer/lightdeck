from __future__ import annotations

import argparse
import sys

from PySide6.QtWidgets import QApplication

from . import APP_ID, APP_NAME, __version__
from .config import load_config
from .ui.main_window import MainWindow, app_icon
from .ui.theme import ThemeManager


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    parser = argparse.ArgumentParser(prog=APP_ID, description=f"{APP_NAME} — desktop remote for Hue lights")
    parser.add_argument("--demo", action="store_true", help="run against simulated lights")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    args, qt_args = parser.parse_known_args(argv[1:])

    QApplication.setApplicationName(APP_NAME)
    QApplication.setApplicationVersion(__version__)
    QApplication.setDesktopFileName(APP_ID)
    app = QApplication([argv[0], *qt_args])
    app.setStyle("Fusion")
    app.setWindowIcon(app_icon())

    config = load_config()
    themes = ThemeManager(app, config.theme)
    themes.apply()

    window = MainWindow(config, themes, demo=args.demo)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
