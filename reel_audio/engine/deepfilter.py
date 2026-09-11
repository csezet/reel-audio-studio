from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Callable

from .tools import ToolError, app_root, find_executable, run_command

CancelCallback = Callable[[], bool]


def _user_component_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return base / "ReelAudioStudio" / "bin"
    return Path.home() / ".reelaudiostudio" / "bin"


def deepfilter_install_path() -> Path:
    name = "deep-filter.exe" if os.name == "nt" else "deep-filter"
    return _user_component_dir() / name


def _deepfilter_executable() -> str | None:
    # Upstream names the Python console entry point deepFilter; precompiled
    # releases may use deep-filter. Support both.
    user_binary = deepfilter_install_path()
    if user_binary.exists():
        return str(user_binary)
    for name in ("deepFilter", "deep-filter"):
        exe = find_executable(name)
        if exe:
            return exe
    script_names = ("deepFilter.exe", "deep-filter.exe") if os.name == "nt" else ("deepFilter", "deep-filter")
    base = Path(sys.executable).resolve().parent
    for script in script_names:
        candidate = base / script
        if candidate.exists():
            return str(candidate)
    return None


def deepfilter_available() -> bool:
    return bool(_deepfilter_executable())


def enhance_with_deepfilter(
    input_wav: Path,
    output_dir: Path,
    *,
    cancel_cb: CancelCallback | None = None,
) -> Path:
    exe = _deepfilter_executable()
    if not exe:
        raise ToolError(
            "DeepFilterNet не установлен. Установите пакет deepfilternet или положите deep-filter рядом с программой."
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    before = set(output_dir.glob("*.wav"))
    run_command([exe, "--output-dir", str(output_dir), str(input_wav)], cancel_cb=cancel_cb)
    candidates = [p for p in output_dir.glob("*.wav") if p not in before]
    if not candidates:
        candidates = list(output_dir.glob("*.wav"))
    if not candidates:
        raise ToolError("DeepFilterNet завершился без выходного WAV-файла.")
    return max(candidates, key=lambda p: p.stat().st_mtime)
