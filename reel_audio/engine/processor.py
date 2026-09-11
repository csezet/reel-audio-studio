from __future__ import annotations

import json
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .deepfilter import enhance_with_deepfilter
from .tools import (
    CancelCallback,
    CommandCancelled,
    ProgressCallback,
    ToolError,
    choose_video_encoder,
    media_summary,
    require_tool,
    run_command,
)
from .vad import intersect_intervals, silero_available, speech_to_nonspeech

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


def _scaled_progress(cb: ProgressCallback | None, start: int, end: int) -> ProgressCallback | None:
    if cb is None:
        return None
    span = max(0, end - start)
    return lambda value: cb(max(start, min(end, start + int(span * value / 100))))


def build_pre_master_filter(settings: ProcessingSettings, *, after_ai_denoise: bool = False) -> str:
    """DSP before loudness normalization/limiting.

    Music mixes are deliberately processed more conservatively: speech-specific
    denoising and a 70 Hz voice high-pass can damage music, so they are skipped
    or softened for the Voice + Music preset.
    """
    music_mix = settings.preset == "Voice + Music"
    filters: list[str] = ["highpass=f=30" if music_mix else "highpass=f=70"]

    if settings.noise_removal > 0 and not after_ai_denoise and not music_mix:
        nr = 4.0 + (settings.noise_removal / 100.0) * 24.0
        filters.append(f"afftdn=nr={nr:.1f}:nf=-50:tn=1:gs=3")

    if settings.voice_presence > 0 and not music_mix:
        gain = (settings.voice_presence / 100.0) * 4.0
        filters.append(f"equalizer=f=3000:t=q:w=1:g={gain:.2f}")

    if settings.compression > 0:
        strength = settings.compression / 100.0
        if music_mix:
            strength *= 0.45
        ratio = 1.4 + strength * 3.6
        makeup_db = 0.5 + strength * 2.0
        makeup = 10 ** (makeup_db / 20.0)
        mix = 0.55 + strength * 0.4
        filters.append(
            "acompressor="
            f"threshold=0.125:ratio={ratio:.2f}:attack=15:release=180:"
            f"makeup={makeup:.3f}:knee=2.8:mix={mix:.2f}"
        )
    return ",".join(filters)


def _loudnorm_filter(settings: ProcessingSettings, stats: dict[str, float] | None = None) -> str:
    base = f"loudnorm=I={settings.target_lufs:.1f}:LRA=9:TP=-1.5"
    if not stats:
        return base
    return (
        base
        + f":measured_I={stats['input_i']:.3f}"
        + f":measured_LRA={stats['input_lra']:.3f}"
        + f":measured_TP={stats['input_tp']:.3f}"
        + f":measured_thresh={stats['input_thresh']:.3f}"
        + f":offset={stats['target_offset']:.3f}:linear=true"
    )


def build_audio_filter(
    settings: ProcessingSettings,
    *,
    after_ai_denoise: bool = False,
    loudnorm_stats: dict[str, float] | None = None,
) -> str:
    filters = [build_pre_master_filter(settings, after_ai_denoise=after_ai_denoise)]
    if settings.auto_normalize:
        filters.append(_loudnorm_filter(settings, loudnorm_stats))
    filters.append("aresample=48000")
    # 10^(-1.5/20) = 0.8414. Disable auto-level; otherwise alimiter applies
    # 1/limit gain and partly undoes the intended ceiling.
    filters.append("alimiter=limit=0.8414:attack=5:release=50:level=false:latency=true")
    return ",".join(x for x in filters if x)


def _parse_loudnorm_stats(text: str) -> dict[str, float] | None:
    matches = list(re.finditer(r'\{\s*"input_i".*?\}', text, re.S))
    if not matches:
        return None
    try:
        raw = json.loads(matches[-1].group(0))
        keys = ("input_i", "input_lra", "input_tp", "input_thresh", "target_offset")
        parsed = {key: float(raw[key]) for key in keys}
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
    if any(value != value or abs(value) == float("inf") for value in parsed.values()):
        return None
    return parsed


def _measure_loudness(
    source: Path,
    settings: ProcessingSettings,
    ffmpeg: str,
    *,
    after_ai_denoise: bool,
    duration: float,
    cancel_cb: CancelCallback | None,
    progress_cb: ProgressCallback | None,
) -> dict[str, float] | None:
    pre = build_pre_master_filter(settings, after_ai_denoise=after_ai_denoise)
    analysis_filter = f"{pre},{_loudnorm_filter(settings)}:print_format=json" if pre else f"{_loudnorm_filter(settings)}:print_format=json"
    proc = run_command(
        [
            ffmpeg, "-hide_banner", "-v", "info", "-i", str(source), "-vn",
            "-af", analysis_filter, "-f", "null", "-",
        ],
        cancel_cb=cancel_cb,
        progress_cb=progress_cb,
        duration=duration,
    )
    return _parse_loudnorm_stats((proc.stderr or "") + "\n" + (proc.stdout or ""))


def _detect_silences_ffmpeg(
    source: Path,
    settings: ProcessingSettings,
    ffmpeg: str,
    *,
    cancel_cb: CancelCallback | None = None,
) -> list[tuple[float, float]]:
    proc = run_command(
        [
            ffmpeg, "-hide_banner", "-nostats", "-i", str(source),
            "-af", f"silencedetect=noise={settings.pause_threshold_db}dB:d={settings.min_pause_seconds}",
            "-f", "null", "-",
        ],
        check=False,
        cancel_cb=cancel_cb,
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


def _trim_media(
    source: Path,
    target: Path,
    segments: list[tuple[float, float]],
    has_video: bool,
    ffmpeg: str,
    *,
    duration: float,
    cancel_cb: CancelCallback | None = None,
    progress_cb: ProgressCallback | None = None,
) -> None:
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
        encoder, encoder_opts = choose_video_encoder(ffmpeg)
        cmd = [
            ffmpeg, "-y", "-v", "error", "-i", str(source),
            "-filter_complex", ";".join(parts),
            "-map", "[vout]", "-map", "[aout]",
            "-c:v", encoder, *encoder_opts, "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(target),
        ]
    else:
        parts.append("".join(labels) + f"concat=n={len(segments)}:v=0:a=1[aout]")
        cmd = [
            ffmpeg, "-y", "-v", "error", "-i", str(source),
            "-filter_complex", ";".join(parts), "-map", "[aout]",
            "-c:a", "pcm_s16le", str(target),
        ]
    run_command(cmd, cancel_cb=cancel_cb, progress_cb=progress_cb, duration=duration)


class AudioProcessor:
    def process(
        self,
        input_path: str | Path,
        output_path: str | Path,
        settings: ProcessingSettings,
        status_cb: StageCallback | None = None,
        progress_cb: ProgressCallback | None = None,
        cancel_cb: CancelCallback | None = None,
    ) -> Path:
        input_path = Path(input_path)
        output_path = Path(output_path)
        ffmpeg = require_tool("ffmpeg")
        info = media_summary(input_path, cancel_cb=cancel_cb)
        if not info["has_audio"]:
            raise ToolError("В выбранном файле не найден аудиопоток.")
        if progress_cb:
            progress_cb(1)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="reelaudio_") as td:
            work = Path(td)
            current = input_path
            current_duration = float(info["duration"] or 0.0)

            if settings.remove_pauses:
                _status(status_cb, "Определяю длинные тихие паузы…")
                level_silences = _detect_silences_ffmpeg(current, settings, ffmpeg, cancel_cb=cancel_cb)
                silences = level_silences
                if settings.ai_vad and silero_available():
                    _status(status_cb, "Silero VAD: проверяю, что в паузах нет речи…")
                    non_speech = speech_to_nonspeech(
                        current, current_duration, ffmpeg, work,
                        cancel_cb=cancel_cb,
                    )
                    # Only low-level audio that is also non-speech can be cut.
                    silences = intersect_intervals(
                        level_silences,
                        non_speech,
                        min_duration=settings.min_pause_seconds,
                    )
                segments = _keep_segments(current_duration, silences, settings.keep_pause_seconds)
                if len(segments) > 1:
                    _status(status_cb, f"Сокращаю паузы: {len(segments)} фрагментов…")
                    trimmed = work / ("trimmed.mp4" if info["has_video"] else "trimmed.wav")
                    _trim_media(
                        current, trimmed, segments, info["has_video"], ffmpeg,
                        duration=current_duration,
                        cancel_cb=cancel_cb,
                        progress_cb=_scaled_progress(progress_cb, 5, 32),
                    )
                    current = trimmed
                    current_duration = sum(max(0.0, end - start) for start, end in segments)
            if progress_cb:
                progress_cb(max(34, 1))

            ai_audio: Path | None = None
            deepfilter_allowed = settings.ai_deepfilter and settings.preset != "Voice + Music"
            if settings.ai_deepfilter and not deepfilter_allowed:
                _status(status_cb, "DeepFilterNet пропущен для Voice + Music, чтобы не портить музыкальный микс.")
            if deepfilter_allowed:
                _status(status_cb, "DeepFilterNet: очищаю голос…")
                noisy = work / "deepfilter_input.wav"
                # Preserve the source channel layout; the previous implementation
                # forced -ac 1 and permanently destroyed stereo information.
                run_command(
                    [
                        ffmpeg, "-y", "-v", "error", "-i", str(current),
                        "-vn", "-ar", "48000", "-c:a", "pcm_s16le", str(noisy),
                    ],
                    cancel_cb=cancel_cb,
                    progress_cb=_scaled_progress(progress_cb, 34, 44),
                    duration=current_duration,
                )
                ai_audio = enhance_with_deepfilter(noisy, work / "deepfilter_out", cancel_cb=cancel_cb)
            if progress_cb:
                progress_cb(46)

            audio_source = ai_audio if ai_audio is not None else current
            loudnorm_stats: dict[str, float] | None = None
            if settings.auto_normalize:
                _status(status_cb, "Измеряю громкость (проход 1/2)…")
                loudnorm_stats = _measure_loudness(
                    audio_source,
                    settings,
                    ffmpeg,
                    after_ai_denoise=ai_audio is not None,
                    duration=current_duration,
                    cancel_cb=cancel_cb,
                    progress_cb=_scaled_progress(progress_cb, 46, 62),
                )
                if loudnorm_stats is None:
                    _status(status_cb, "Не удалось получить measured LUFS — использую безопасную однопроходную нормализацию.")

            _status(status_cb, "EQ, компрессия и финальный мастеринг (проход 2/2)…" if settings.auto_normalize else "EQ, компрессия и финальный мастеринг…")
            afilter = build_audio_filter(
                settings,
                after_ai_denoise=ai_audio is not None,
                loudnorm_stats=loudnorm_stats,
            )

            if info["has_video"]:
                cmd = [ffmpeg, "-y", "-v", "error", "-i", str(current)]
                if ai_audio is not None:
                    cmd += ["-i", str(ai_audio), "-map", "0:v:0", "-map", "1:a:0"]
                else:
                    cmd += ["-map", "0:v:0", "-map", "0:a:0"]
                cmd += [
                    "-c:v", "copy", "-af", afilter,
                    "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                    "-movflags", "+faststart", "-shortest", str(output_path),
                ]
            else:
                suffix = output_path.suffix.lower()
                codec = ["-c:a", "pcm_s16le"] if suffix == ".wav" else ["-c:a", "aac", "-b:a", "192k"]
                cmd = [ffmpeg, "-y", "-v", "error", "-i", str(audio_source), "-af", afilter] + codec + [str(output_path)]

            run_command(
                cmd,
                cancel_cb=cancel_cb,
                progress_cb=_scaled_progress(progress_cb, 62, 100),
                duration=current_duration,
            )
            if cancel_cb and cancel_cb():
                raise CommandCancelled("Операция отменена.")
            _status(status_cb, "Готово")
            if progress_cb:
                progress_cb(100)
        return output_path
