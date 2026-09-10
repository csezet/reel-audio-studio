from __future__ import annotations

from pathlib import Path

from .tools import ToolError, run_command

_model = None


def silero_available() -> bool:
    try:
        import silero_vad  # noqa: F401
        return True
    except Exception:
        return False


def speech_to_silences(
    source: Path,
    duration: float,
    ffmpeg: str,
    work_dir: Path,
    threshold: float = 0.5,
) -> list[tuple[float, float]]:
    global _model
    try:
        from silero_vad import get_speech_timestamps, load_silero_vad, read_audio
    except Exception as exc:
        raise ToolError("Silero VAD не установлен. Установите silero-vad или отключите AI VAD.") from exc

    wav = work_dir / "vad_16k.wav"
    run_command([
        ffmpeg, "-y", "-v", "error", "-i", str(source),
        "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)
    ])

    if _model is None:
        _model = load_silero_vad()
    audio = read_audio(str(wav))
    speech = get_speech_timestamps(
        audio,
        _model,
        sampling_rate=16000,
        threshold=threshold,
        return_seconds=True,
    )
    speech_ranges = [(float(s["start"]), float(s["end"])) for s in speech]
    silences: list[tuple[float, float]] = []
    cursor = 0.0
    for start, end in speech_ranges:
        if start > cursor:
            silences.append((cursor, start))
        cursor = max(cursor, end)
    if duration > cursor:
        silences.append((cursor, duration))
    return silences
