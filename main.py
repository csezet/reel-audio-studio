from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

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
