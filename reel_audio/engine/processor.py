from __future__ import annotations

import math
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .deepfilter import enhance_with_deepfilter
from .tools import ToolError, media_summary, require_tool, run_command
from .vad import silero_available, speech_to_silences

StageCallback = Callable[[str], None]


@dataclass(slots=True)
class ProcessingSettings:
    preset: str = "Voice Clean"
    noise_removal: int = 55
    voice_presence: int = 45
    compression: int = 50
    remove_pauses: bool = False
    pause_threshold_db: int = -42
    min_pause_seconds: float = 0.75
    keep_pause_seconds: float = 0.18
    target_lufs: float = -14.0
    auto_normalize: bool = True
    ai_deepfilter: bool = False
    ai_vad: bool = False


def _status(cb: StageCallback | None, text: str) -> None:
    if cb:
        cb(text)


def build_audio_filter(settings: ProcessingSettings, *, after_ai_denoise: bool = False) -> str:
    filters: list[str] = ["highpass=f=70"]

    if settings.noise_removal > 0 and not after_ai_denoise:
        nr = 4.0 + (settings.noise_removal / 100.0) * 24.0
        filters.append(f"afftdn=nr={nr:.1f}:nf=-50:tn=1:gs=3")

    if settings.voice_presence > 0:
        gain = (settings.voice_presence / 100.0) * 4.0
        filters.append(f"equalizer=f=3000:t=q:w=1:g={gain:.2f}")

    if settings.compression > 0:
        strength = settings.compression / 100.0
        ratio = 1.4 + strength * 3.6
        makeup_db = 0.5 + strength * 2.0
        makeup = 10 ** (makeup_db / 20.0)
        mix = 0.55 + strength * 0.4
        filters.append(
            "acompressor="
            f"threshold=0.125:ratio={ratio:.2f}:attack=15:release=180:"
            f"makeup={makeup:.3f}:knee=2.8:mix={mix:.2f}"
        )

    if settings.auto_normalize:
        filters.append(f"loudnorm=I={settings.target_lufs:.1f}:LRA=9:TP=-1.5")
    filters.append("aresample=48000")
    filters.append("alimiter=limit=0.95:attack=5:release=50")
    return ",".join(filters)


def _detect_silences_ffmpeg(source: Path, settings: ProcessingSettings, ffmpeg: str) -> list[tuple[float, float]]:
    proc = run_command(
        [
            ffmpeg, "-hide_banner", "-nostats", "-i", str(source),
            "-af", f"silencedetect=noise={settings.pause_threshold_db}dB:d={settings.min_pause_seconds}",
            "-f", "null", "-"
        ],
        check=False,
    )
    text = (proc.stderr or "") + "\n" + (proc.stdout or "")
    starts = [float(x) for x in re.findall(r"silence_start:\s*([0-9.]+)", text)]
    ends = [float(x) for x in re.findall(r"silence_end:\s*([0-9.]+)", text)]
    intervals: list[tuple[float, float]] = []
    for start, end in zip(starts, ends):
        if end > start:
            intervals.append((start, end))
    return intervals


def _keep_segments(duration: float, silences: list[tuple[float, float]], keep_silence: float) -> list[tuple[float, float]]:
    if duration <= 0:
        return []
    remove_ranges: list[tuple[float, float]] = []
    half = max(0.0, keep_silence) / 2.0
    for start, end in silences:
        if end <= start:
            continue
        cut_start = max(0.0, start + half)
        cut_end = min(duration, end - half)
        if cut_end - cut_start > 0.04:
            remove_ranges.append((cut_start, cut_end))

    if not remove_ranges:
        return [(0.0, duration)]

    segments: list[tuple[float, float]] = []
    cursor = 0.0
    for start, end in sorted(remove_ranges):
        if start > cursor + 0.04:
            segments.append((cursor, start))
        cursor = max(cursor, end)
    if duration > cursor + 0.04:
        segments.append((cursor, duration))
    return segments


def _trim_media(source: Path, target: Path, segments: list[tuple[float, float]], has_video: bool, ffmpeg: str) -> None:
    if not segments:
        raise ToolError("После удаления пауз не осталось материала для экспорта.")
    if len(segments) > 100:
        raise ToolError("Найдено слишком много пауз (>100). Увеличьте минимальную длину паузы.")

    parts: list[str] = []
    labels: list[str] = []
    for i, (start, end) in enumerate(segments):
        if has_video:
            parts.append(f"[0:v]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS[v{i}]")
            parts.append(f"[0:a]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS[a{i}]")
            labels.append(f"[v{i}][a{i}]")
        else:
            parts.append(f"[0:a]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS[a{i}]")
            labels.append(f"[a{i}]")

    if has_video:
        parts.append("".join(labels) + f"concat=n={len(segments)}:v=1:a=1[vout][aout]")
        cmd = [
            ffmpeg, "-y", "-v", "error", "-i", str(source),
            "-filter_complex", ";".join(parts),
            "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(target)
        ]
    else:
        parts.append("".join(labels) + f"concat=n={len(segments)}:v=0:a=1[aout]")
        cmd = [
            ffmpeg, "-y", "-v", "error", "-i", str(source),
            "-filter_complex", ";".join(parts), "-map", "[aout]",
            "-c:a", "pcm_s16le", str(target)
        ]
    run_command(cmd)


class AudioProcessor:
    def process(
        self,
        input_path: str | Path,
        output_path: str | Path,
        settings: ProcessingSettings,
        status_cb: StageCallback | None = None,
    ) -> Path:
        input_path = Path(input_path)
        output_path = Path(output_path)
        ffmpeg = require_tool("ffmpeg")
        info = media_summary(input_path)
        if not info["has_audio"]:
            raise ToolError("В выбранном файле не найден аудиопоток.")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="reelaudio_") as td:
            work = Path(td)
            current = input_path

            if settings.remove_pauses:
                _status(status_cb, "Определяю речь и длинные паузы…")
                if settings.ai_vad and silero_available():
                    silences = speech_to_silences(current, info["duration"], ffmpeg, work)
                else:
                    silences = _detect_silences_ffmpeg(current, settings, ffmpeg)
                segments = _keep_segments(info["duration"], silences, settings.keep_pause_seconds)
                if len(segments) > 1:
                    _status(status_cb, f"Сокращаю паузы: {len(segments)} фрагментов…")
                    trimmed = work / ("trimmed.mp4" if info["has_video"] else "trimmed.wav")
                    _trim_media(current, trimmed, segments, info["has_video"], ffmpeg)
                    current = trimmed

            ai_audio: Path | None = None
            if settings.ai_deepfilter:
                _status(status_cb, "DeepFilterNet: очищаю голос…")
                noisy = work / "deepfilter_input.wav"
                run_command([
                    ffmpeg, "-y", "-v", "error", "-i", str(current),
                    "-vn", "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le", str(noisy)
                ])
                ai_audio = enhance_with_deepfilter(noisy, work / "deepfilter_out")

            _status(status_cb, "EQ, компрессия и финальная громкость…")
            afilter = build_audio_filter(settings, after_ai_denoise=ai_audio is not None)

            if info["has_video"]:
                cmd = [ffmpeg, "-y", "-v", "error", "-i", str(current)]
                if ai_audio is not None:
                    cmd += ["-i", str(ai_audio), "-map", "0:v:0", "-map", "1:a:0"]
                else:
                    cmd += ["-map", "0:v:0", "-map", "0:a:0"]
                cmd += [
                    "-c:v", "copy", "-af", afilter,
                    "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                    "-movflags", "+faststart", "-shortest", str(output_path)
                ]
            else:
                src = ai_audio if ai_audio is not None else current
                suffix = output_path.suffix.lower()
                codec = ["-c:a", "pcm_s16le"] if suffix == ".wav" else ["-c:a", "aac", "-b:a", "192k"]
                cmd = [ffmpeg, "-y", "-v", "error", "-i", str(src), "-af", afilter] + codec + [str(output_path)]

            run_command(cmd)
            _status(status_cb, "Готово")
        return output_path
