from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


def log_directory() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return base / "ReelAudioStudio" / "logs"
    return Path.home() / ".reelaudiostudio" / "logs"


def configure_logging() -> Path | None:
    """Configure a small rotating diagnostic log without affecting the UI."""
    try:
        directory = log_directory()
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "reel_audio.log"
        root = logging.getLogger()
        root.setLevel(logging.INFO)
        if not any(isinstance(h, RotatingFileHandler) and getattr(h, "baseFilename", "") == str(path) for h in root.handlers):
            handler = RotatingFileHandler(path, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
            root.addHandler(handler)
        return path
    except Exception:
        # Logging must never prevent the editor from starting.
        return None
