from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable


log = logging.getLogger(__name__)


class ToolError(RuntimeError):
    pass


class CommandCancelled(ToolError):
    """Raised when a long-running child process is cancelled by the UI."""


CancelCallback = Callable[[], bool]
ProgressCallback = Callable[[int], None]


def app_root() -> Path:
    """Directory next to the installed executable (or project root in source mode)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def resource_root() -> Path:
    """Read-only bundle resources. PyInstaller 6 onedir usually maps this to _MEIPASS."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", app_root())).resolve()
    return app_root()


def find_executable(name: str) -> str | None:
    exe = f"{name}.exe" if os.name == "nt" and not name.lower().endswith(".exe") else name
    for root in (resource_root(), app_root()):
        bundled = root / "bin" / exe
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


def _creationflags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def _stop_process(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
    except Exception:
        pass
    try:
        proc.wait(timeout=0.8)
        return
    except Exception:
        pass
    try:
        proc.kill()
    except Exception:
        pass
    try:
        proc.wait(timeout=1.0)
    except Exception:
        pass


def run_command(
    args: list[str],
    *,
    capture: bool = True,
    check: bool = True,
    cwd: str | Path | None = None,
    cancel_cb: CancelCallback | None = None,
    progress_cb: ProgressCallback | None = None,
    duration: float | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a command with cooperative cancellation and optional FFmpeg progress.

    When ``progress_cb`` is supplied for FFmpeg, ``-progress pipe:1`` is added and
    ``out_time_us``/``out_time_ms`` are converted into 0..100 percent.  The
    function is normally called from a worker thread, never the GUI thread.
    """
    cmd = list(args)
    is_ffmpeg = bool(cmd) and Path(cmd[0]).stem.lower() == "ffmpeg"
    if progress_cb is not None and is_ffmpeg and "-progress" not in cmd:
        # Put global progress options immediately after the executable.
        cmd[1:1] = ["-progress", "pipe:1", "-nostats"]

    log.debug("run command: %s", " ".join(str(x) for x in cmd))
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.PIPE if capture else subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        creationflags=_creationflags(),
    )

    if progress_cb is not None and is_ffmpeg and capture:
        stderr_lines: list[str] = []

        def drain_stderr() -> None:
            if proc.stderr is None:
                return
            for line in proc.stderr:
                stderr_lines.append(line)

        err_thread = threading.Thread(target=drain_stderr, daemon=True)
        err_thread.start()
        stdout_lines: list[str] = []
        last_percent = -1
        if progress_cb:
            progress_cb(0)
        try:
            assert proc.stdout is not None
            while True:
                if cancel_cb and cancel_cb():
                    _stop_process(proc)
                    raise CommandCancelled("Операция отменена.")
                line = proc.stdout.readline()
                if line:
                    stdout_lines.append(line)
                    key, sep, value = line.strip().partition("=")
                    if sep and duration and duration > 0 and key in {"out_time_us", "out_time_ms"}:
                        try:
                            # FFmpeg historically reports both fields in microseconds.
                            elapsed = float(value) / 1_000_000.0
                            pct = max(0, min(99, int(elapsed / duration * 100)))
                            if pct != last_percent:
                                last_percent = pct
                                progress_cb(pct)
                        except ValueError:
                            pass
                elif proc.poll() is not None:
                    break
                else:
                    time.sleep(0.03)
        finally:
            if proc.stdout:
                proc.stdout.close()
        return_code = proc.wait()
        err_thread.join(timeout=1.0)
        if progress_cb and return_code == 0:
            progress_cb(100)
        stdout = "".join(stdout_lines)
        stderr = "".join(stderr_lines)
    else:
        stdout = ""
        stderr = ""
        while True:
            if cancel_cb and cancel_cb():
                _stop_process(proc)
                raise CommandCancelled("Операция отменена.")
            try:
                out, err = proc.communicate(timeout=0.2)
                stdout = out or ""
                stderr = err or ""
                break
            except subprocess.TimeoutExpired:
                continue
        return_code = proc.returncode

    result = subprocess.CompletedProcess(cmd, return_code, stdout, stderr)
    if check and return_code != 0:
        tail = (stderr or stdout or "")[-5000:]
        log.error("command failed rc=%s: %s\n%s", return_code, " ".join(str(x) for x in cmd), tail)
        raise ToolError(f"Команда завершилась с ошибкой ({return_code}).\n{tail}")
    return result


def probe_media(path: str | Path, *, cancel_cb: CancelCallback | None = None) -> dict:
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
        ],
        cancel_cb=cancel_cb,
    )
    return json.loads(proc.stdout or "{}")


def media_summary(path: str | Path, *, cancel_cb: CancelCallback | None = None) -> dict:
    data = probe_media(path, cancel_cb=cancel_cb)
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


def available_encoders(ffmpeg: str | None = None) -> set[str]:
    ffmpeg = ffmpeg or require_tool("ffmpeg")
    proc = run_command([ffmpeg, "-hide_banner", "-encoders"], check=False)
    encoders: set[str] = set()
    for line in (proc.stdout or "").splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] and parts[0][0] in {"V", "A", "."}:
            encoders.add(parts[1])
    return encoders


def choose_video_encoder(ffmpeg: str | None = None) -> tuple[str, list[str]]:
    """Choose an available video encoder without assuming libx264 exists.

    Windows Media Foundation H.264 is preferred on Windows. libx264 is only
    selected if the user's FFmpeg build actually exposes it (which means that
    particular FFmpeg build already opted into GPL components). MPEG-4 Part 2
    is the final built-in fallback.
    """
    encoders = available_encoders(ffmpeg)
    candidates: list[tuple[str, list[str]]] = []
    if os.name == "nt":
        candidates.append(("h264_mf", ["-b:v", "8M"]))
    candidates.extend([
        ("libopenh264", ["-b:v", "8M"]),
        ("libx264", ["-preset", "veryfast", "-crf", "18"]),
        ("mpeg4", ["-q:v", "2"]),
    ])
    for name, options in candidates:
        if name in encoders:
            return name, options
    raise ToolError("В этой сборке FFmpeg не найден подходящий видеоэнкодер для изменения таймлайна.")
