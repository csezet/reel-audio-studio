from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Callable

from .tools import CancelCallback, ProgressCallback, ToolError, choose_video_encoder, media_summary, require_tool, run_command

StageCallback = Callable[[str], None]


VIDEO_QUALITIES = {
    "Без доп. перекодирования": None,
    "Высокое": {"crf": "18", "video_bitrate": "10M", "audio_bitrate": "256k"},
    "Стандартное": {"crf": "20", "video_bitrate": "7M", "audio_bitrate": "192k"},
    "Компактное": {"crf": "23", "video_bitrate": "4M", "audio_bitrate": "160k"},
}

AUDIO_QUALITIES = {
    "Без доп. перекодирования": None,
    "Высокое": {"audio_bitrate": "256k"},
    "Стандартное": {"audio_bitrate": "192k"},
    "Компактное": {"audio_bitrate": "128k"},
}


def _status(cb: StageCallback | None, text: str) -> None:
    if cb:
        cb(text)


def _atomic_copy(
    source: Path,
    destination: Path,
    *,
    cancel_cb: CancelCallback | None = None,
    progress_cb: ProgressCallback | None = None,
) -> None:
    """Copy through a same-directory temporary file and commit atomically.

    Copying is chunked so a multi-gigabyte Reel can still be cancelled and the
    UI can report deterministic progress.  The destination is replaced only
    after the temporary file is fully written.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{destination.stem}_", suffix=destination.suffix, dir=destination.parent)
    os.close(fd)
    tmp = Path(tmp_name)
    total = max(1, source.stat().st_size)
    copied = 0
    try:
        with source.open("rb") as src, tmp.open("wb") as dst:
            while True:
                if cancel_cb and cancel_cb():
                    from .tools import CommandCancelled
                    raise CommandCancelled("Экспорт отменён.")
                block = src.read(4 * 1024 * 1024)
                if not block:
                    break
                dst.write(block)
                copied += len(block)
                if progress_cb:
                    progress_cb(min(99, int(copied / total * 100)))
            dst.flush()
            os.fsync(dst.fileno())
        shutil.copystat(source, tmp)
        os.replace(tmp, destination)
        if progress_cb:
            progress_cb(100)
    finally:
        tmp.unlink(missing_ok=True)


def export_media(
    source: str | Path,
    destination: str | Path,
    *,
    format_name: str,
    quality: str,
    status_cb: StageCallback | None = None,
    progress_cb: ProgressCallback | None = None,
    cancel_cb: CancelCallback | None = None,
) -> Path:
    source = Path(source)
    destination = Path(destination)
    info = media_summary(source, cancel_cb=cancel_cb)
    duration = float(info.get("duration") or 0.0)

    is_video_output = format_name.startswith("MP4")
    is_wav_output = format_name.startswith("WAV")
    expected_suffix = ".mp4" if is_video_output else (".wav" if is_wav_output else ".m4a")
    if destination.suffix.lower() != expected_suffix:
        destination = destination.with_suffix(expected_suffix)

    if quality == "Без доп. перекодирования" and destination.suffix.lower() == source.suffix.lower():
        _status(status_cb, "Сохраняю готовый результат без дополнительного перекодирования…")
        _atomic_copy(source, destination, cancel_cb=cancel_cb, progress_cb=progress_cb)
        return destination

    ffmpeg = require_tool("ffmpeg")
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{destination.stem}_", suffix=destination.suffix, dir=destination.parent)
    os.close(fd)
    tmp = Path(tmp_name)
    tmp.unlink(missing_ok=True)  # ffmpeg creates it itself

    try:
        _status(status_cb, "Экспортирую выбранное качество…")
        cmd = [ffmpeg, "-y", "-v", "error", "-i", str(source)]
        if is_video_output:
            if not info.get("has_video"):
                raise ToolError("Нельзя экспортировать аудиофайл как MP4 без видеопотока.")
            encoder, encoder_opts = choose_video_encoder(ffmpeg)
            selected = VIDEO_QUALITIES.get(quality) or VIDEO_QUALITIES["Стандартное"]
            if encoder == "libx264":
                encoder_opts = ["-preset", "medium", "-crf", selected["crf"]]
            elif encoder == "mpeg4":
                q = {"18": "2", "20": "3", "23": "5"}.get(selected["crf"], "3")
                encoder_opts = ["-q:v", q]
            else:
                encoder_opts = ["-b:v", selected["video_bitrate"]]
            cmd += [
                "-map", "0:v:0", "-map", "0:a:0?", "-c:v", encoder, *encoder_opts,
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", selected["audio_bitrate"],
                "-movflags", "+faststart", str(tmp),
            ]
        elif is_wav_output:
            cmd += ["-vn", "-c:a", "pcm_s24le", "-ar", "48000", str(tmp)]
        else:
            selected = AUDIO_QUALITIES.get(quality) or AUDIO_QUALITIES["Стандартное"]
            cmd += ["-vn", "-c:a", "aac", "-b:a", selected["audio_bitrate"], "-ar", "48000", str(tmp)]

        run_command(cmd, cancel_cb=cancel_cb, progress_cb=progress_cb, duration=duration)
        os.replace(tmp, destination)
        return destination
    finally:
        tmp.unlink(missing_ok=True)
