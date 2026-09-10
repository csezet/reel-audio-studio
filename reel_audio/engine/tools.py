from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable


class ToolError(RuntimeError):
    pass


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def find_executable(name: str) -> str | None:
    exe = f"{name}.exe" if os.name == "nt" and not name.lower().endswith(".exe") else name
    bundled = app_root() / "bin" / exe
    if bundled.exists():
        return str(bundled)
    return shutil.which(name) or (shutil.which(exe) if exe != name else None)


def require_tool(name: str) -> str:
    path = find_executable(name)
    if not path:
        raise ToolError(
            f"Не найден {name}. Установите FFmpeg или положите {name}.exe в папку bin рядом с программой."
        )
    return path


def run_command(
    args: list[str],
    *,
    capture: bool = True,
    check: bool = True,
    cwd: str | Path | None = None,
) -> subprocess.CompletedProcess[str]:
    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    proc = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creationflags,
    )
    if check and proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "")[-5000:]
        raise ToolError(f"Команда завершилась с ошибкой ({proc.returncode}).\n{tail}")
    return proc


def probe_media(path: str | Path) -> dict:
    ffprobe = require_tool("ffprobe")
    proc = run_command(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=index,codec_type,codec_name,width,height,sample_rate,channels",
            "-of",
            "json",
            str(path),
        ]
    )
    return json.loads(proc.stdout or "{}")


def media_summary(path: str | Path) -> dict:
    data = probe_media(path)
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    try:
        duration = float(data.get("format", {}).get("duration", 0) or 0)
    except (TypeError, ValueError):
        duration = 0.0
    return {
        "duration": duration,
        "has_video": video is not None,
        "has_audio": audio is not None,
        "video": video or {},
        "audio": audio or {},
    }
