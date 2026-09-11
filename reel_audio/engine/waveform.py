from __future__ import annotations

import array
import os
import subprocess
from pathlib import Path
from typing import Callable

from .tools import CommandCancelled, require_tool

CancelCallback = Callable[[], bool]


def waveform_peaks(
    path: str | Path,
    points: int = 900,
    *,
    duration: float | None = None,
    cancel_cb: CancelCallback | None = None,
) -> list[float]:
    """Decode a lightweight mono stream and calculate peaks incrementally.

    The old implementation buffered the entire decoded file in RAM.  This one
    processes FFmpeg's f32le stream in chunks and keeps only the peak bins.
    """
    ffmpeg = require_tool("ffmpeg")
    sample_rate = 8000
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    proc = subprocess.Popen(
        [ffmpeg, "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(sample_rate), "-f", "f32le", "-"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=creationflags,
    )

    samples_per_bin = max(1, int((duration or 0.0) * sample_rate / max(1, points))) if duration else 2048
    peaks: list[float] = []
    current_peak = 0.0
    current_count = 0
    remainder = bytearray()

    try:
        assert proc.stdout is not None
        while True:
            if cancel_cb and cancel_cb():
                proc.kill()
                proc.wait(timeout=1.0)
                raise CommandCancelled("Построение waveform отменено.")
            chunk = proc.stdout.read(64 * 1024)
            if not chunk:
                break
            remainder.extend(chunk)
            aligned = (len(remainder) // 4) * 4
            if not aligned:
                continue
            vals = array.array("f")
            vals.frombytes(remainder[:aligned])
            del remainder[:aligned]
            for value in vals:
                current_peak = max(current_peak, abs(float(value)))
                current_count += 1
                if current_count >= samples_per_bin:
                    peaks.append(min(1.0, current_peak))
                    current_peak = 0.0
                    current_count = 0
                    if duration and len(peaks) >= points:
                        # Drain/stop early once all requested bins are filled.
                        proc.kill()
                        break
            if duration and len(peaks) >= points:
                break
        if current_count and len(peaks) < points:
            peaks.append(min(1.0, current_peak))
    finally:
        if proc.stdout:
            proc.stdout.close()

    if proc.poll() is None:
        proc.wait(timeout=2.0)
    stderr = b""
    if proc.stderr:
        stderr = proc.stderr.read() or b""
        proc.stderr.close()
    if proc.returncode not in (0, -9, 1) and not peaks:
        return []
    return peaks[:points]
