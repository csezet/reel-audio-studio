from __future__ import annotations

import array
import math
import os
import subprocess
from pathlib import Path

from .tools import require_tool


def waveform_peaks(path: str | Path, points: int = 900) -> list[float]:
    ffmpeg = require_tool("ffmpeg")
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    proc = subprocess.run(
        [ffmpeg, "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", "8000", "-f", "f32le", "-"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=creationflags,
    )
    if proc.returncode != 0 or not proc.stdout:
        return []
    vals = array.array("f")
    vals.frombytes(proc.stdout)
    if not vals:
        return []
    block = max(1, len(vals) // points)
    peaks: list[float] = []
    for i in range(0, len(vals), block):
        chunk = vals[i : i + block]
        peak = max((abs(v) for v in chunk), default=0.0)
        peaks.append(min(1.0, float(peak)))
        if len(peaks) >= points:
            break
    return peaks
