from __future__ import annotations

import os
import sys
from pathlib import Path

from .tools import ToolError, find_executable, run_command


def _deepfilter_executable() -> str | None:
    exe = find_executable("deepFilter")
    if exe:
        return exe
    # pip installs console scripts next to the active Python executable.  When
    # the app is launched from its .venv that Scripts directory is not always
    # inherited in PATH, so check it explicitly.
    script = "deepFilter.exe" if os.name == "nt" else "deepFilter"
    candidate = Path(sys.executable).resolve().parent / script
    return str(candidate) if candidate.exists() else None


def deepfilter_available() -> bool:
    return bool(_deepfilter_executable())


def enhance_with_deepfilter(input_wav: Path, output_dir: Path) -> Path:
    exe = _deepfilter_executable()
    if not exe:
        raise ToolError(
            "DeepFilterNet не установлен. Установите пакет deepfilternet или отключите AI Noise Removal."
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    before = set(output_dir.glob("*.wav"))
    run_command([exe, "--output-dir", str(output_dir), str(input_wav)])
    candidates = [p for p in output_dir.glob("*.wav") if p not in before]
    if not candidates:
        candidates = list(output_dir.glob("*.wav"))
    if not candidates:
        raise ToolError("DeepFilterNet завершился без выходного WAV-файла.")
    return max(candidates, key=lambda p: p.stat().st_mtime)
