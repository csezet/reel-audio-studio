from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication

from reel_audio.logging_setup import configure_logging
from reel_audio.ui import MainWindow


def _asset(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / "assets" / name


def main() -> int:
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("reelaudiostudio.desktop.1.0")
    except Exception:
        pass

    configure_logging()
    # Qt 6 uses device-independent pixels; PassThrough avoids coarse rounding
    # at Windows 125/150/175% scale factors.
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName("Reel Audio Studio")
    app.setOrganizationName("ReelAudioStudio")
    app.setStyle("Fusion")
    icon = _asset("reel_audio.ico")
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))
    window = MainWindow()
    if icon.exists():
        window.setWindowIcon(QIcon(str(icon)))
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
