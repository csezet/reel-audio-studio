from __future__ import annotations

import array
import hashlib
import os
import subprocess
from pathlib import Path
from typing import Callable

from .tools import CommandCancelled, ToolError, app_root, resource_root

CancelCallback = Callable[[], bool]

SILERO_VERSION = "v6.2.1"
SILERO_MODEL_URL = (
    "https://github.com/snakers4/silero-vad/raw/"
    f"{SILERO_VERSION}/src/silero_vad/data/silero_vad.onnx"
)
SILERO_MODEL_SHA256 = "1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3"

_session = None
_session_path: Path | None = None


def _user_model_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return base / "ReelAudioStudio" / "models"
    return Path.home() / ".reelaudiostudio" / "models"


def silero_model_candidates() -> list[Path]:
    candidates = [resource_root() / "models" / "silero_vad.onnx"]
    if app_root() != resource_root():
        candidates.append(app_root() / "models" / "silero_vad.onnx")
    candidates.append(_user_model_dir() / "silero_vad.onnx")
    return candidates


def silero_model_install_path() -> Path:
    """Writable per-user location used by the in-app model installer."""
    return _user_model_dir() / "silero_vad.onnx"


def silero_model_path() -> Path | None:
    for path in silero_model_candidates():
        if path.is_file():
            return path
    return None


def verify_silero_model(path: str | Path) -> bool:
    path = Path(path)
    if not path.is_file():
        return False
    digest = hashlib.sha256()
    try:
        with path.open("rb") as fh:
            for block in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(block)
    except OSError:
        return False
    return digest.hexdigest().lower() == SILERO_MODEL_SHA256


def silero_available() -> bool:
    path = silero_model_path()
    if path is None or not verify_silero_model(path):
        return False
    try:
        import numpy  # noqa: F401
        import onnxruntime  # noqa: F401
        return True
    except Exception:
        return False


def _load_session():
    global _session, _session_path
    path = silero_model_path()
    if path is None:
        raise ToolError("Модель Silero VAD не найдена. Установите её в Настройках.")
    if not verify_silero_model(path):
        raise ToolError("Файл Silero VAD повреждён или имеет неизвестную версию. Переустановите модель.")
    if _session is not None and _session_path == path:
        return _session
    try:
        import onnxruntime as ort
    except Exception as exc:
        raise ToolError("ONNX Runtime не установлен. Установите Silero VAD в Настройках.") from exc

    opts = ort.SessionOptions()
    opts.inter_op_num_threads = 1
    opts.intra_op_num_threads = 1
    providers = ["CPUExecutionProvider"] if "CPUExecutionProvider" in ort.get_available_providers() else None
    _session = ort.InferenceSession(str(path), sess_options=opts, providers=providers)
    _session_path = path
    return _session


def _speech_ranges_from_probs(
    probs: list[float],
    audio_length_samples: int,
    *,
    threshold: float = 0.5,
    sample_rate: int = 16000,
    frame_samples: int = 512,
    min_speech_duration_ms: int = 250,
    min_silence_duration_ms: int = 100,
    speech_pad_ms: int = 30,
) -> list[tuple[float, float]]:
    """Convert frame probabilities into padded speech ranges.

    This mirrors the core hysteresis used by upstream Silero VAD while keeping
    only the behavior Reel Audio Studio needs: speech start/end detection,
    minimum speech length and edge padding.  Long speech is intentionally not
    force-split because these ranges are used as a *protection mask* for pause
    removal, not as transcription chunks.
    """
    neg_threshold = max(threshold - 0.15, 0.01)
    min_speech = sample_rate * min_speech_duration_ms / 1000.0
    min_silence = sample_rate * min_silence_duration_ms / 1000.0
    pad = int(sample_rate * speech_pad_ms / 1000.0)

    triggered = False
    temp_end: int | None = None
    current_start = 0
    raw: list[tuple[int, int]] = []

    for i, prob in enumerate(probs):
        cur = i * frame_samples
        if prob >= threshold:
            temp_end = None
            if not triggered:
                triggered = True
                current_start = cur
            continue

        if triggered and prob < neg_threshold:
            if temp_end is None:
                temp_end = cur
            if cur - temp_end >= min_silence:
                if temp_end - current_start > min_speech:
                    raw.append((current_start, temp_end))
                triggered = False
                temp_end = None

    if triggered and audio_length_samples - current_start > min_speech:
        raw.append((current_start, audio_length_samples))

    if not raw:
        return []

    padded: list[list[int]] = [[s, e] for s, e in raw]
    for i, pair in enumerate(padded):
        if i == 0:
            pair[0] = max(0, pair[0] - pad)
        if i == len(padded) - 1:
            pair[1] = min(audio_length_samples, pair[1] + pad)
            continue
        gap = padded[i + 1][0] - pair[1]
        if gap < 2 * pad:
            half = max(0, gap // 2)
            pair[1] += half
            padded[i + 1][0] = max(0, padded[i + 1][0] - half)
        else:
            pair[1] = min(audio_length_samples, pair[1] + pad)
            padded[i + 1][0] = max(0, padded[i + 1][0] - pad)

    return [(s / sample_rate, e / sample_rate) for s, e in padded if e > s]


def speech_ranges(
    source: Path,
    ffmpeg: str,
    work_dir: Path,
    *,
    threshold: float = 0.5,
    cancel_cb: CancelCallback | None = None,
) -> list[tuple[float, float]]:
    """Return speech intervals using Silero's ONNX model without PyTorch.

    FFmpeg performs decoding/resampling and streams mono float32 PCM.  Only a
    512-sample frame, Silero's 64-sample context and its recurrent state are
    retained, so long videos do not need to be loaded fully into memory.
    """
    del work_dir  # kept in the public signature for backwards compatibility
    try:
        import numpy as np
    except Exception as exc:
        raise ToolError("NumPy не установлен. Установите Silero VAD в Настройках.") from exc

    session = _load_session()
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    proc = subprocess.Popen(
        [
            ffmpeg, "-hide_banner", "-v", "error", "-i", str(source),
            "-vn", "-ac", "1", "-ar", "16000", "-f", "f32le", "-",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=creationflags,
    )

    state = np.zeros((2, 1, 128), dtype=np.float32)
    context = np.zeros((1, 64), dtype=np.float32)
    sr = np.array(16000, dtype=np.int64)
    pending = bytearray()
    probs: list[float] = []
    total_samples = 0

    try:
        assert proc.stdout is not None
        while True:
            if cancel_cb and cancel_cb():
                proc.kill()
                proc.wait(timeout=1.0)
                raise CommandCancelled("Silero VAD отменён.")
            chunk = proc.stdout.read(64 * 1024)
            if not chunk:
                break
            pending.extend(chunk)
            frame_bytes = 512 * 4
            while len(pending) >= frame_bytes:
                raw = bytes(pending[:frame_bytes])
                del pending[:frame_bytes]
                values = np.frombuffer(raw, dtype=np.float32).reshape(1, 512)
                model_input = np.concatenate((context, values), axis=1)
                out, state = session.run(None, {"input": model_input, "state": state, "sr": sr})
                probs.append(float(np.asarray(out).reshape(-1)[0]))
                context = model_input[:, -64:].copy()
                total_samples += 512

        if pending:
            vals = array.array("f")
            aligned = (len(pending) // 4) * 4
            if aligned:
                vals.frombytes(pending[:aligned])
            count = len(vals)
            if count:
                frame = np.zeros((1, 512), dtype=np.float32)
                frame[0, : min(512, count)] = np.asarray(vals[:512], dtype=np.float32)
                model_input = np.concatenate((context, frame), axis=1)
                out, state = session.run(None, {"input": model_input, "state": state, "sr": sr})
                probs.append(float(np.asarray(out).reshape(-1)[0]))
                total_samples += min(512, count)
    finally:
        if proc.stdout:
            proc.stdout.close()

    if proc.poll() is None:
        proc.wait(timeout=3.0)
    stderr = b""
    if proc.stderr:
        stderr = proc.stderr.read() or b""
        proc.stderr.close()
    if proc.returncode != 0:
        raise ToolError("FFmpeg не смог подготовить звук для Silero VAD.\n" + stderr.decode("utf-8", errors="replace")[-1200:])

    return _speech_ranges_from_probs(probs, total_samples, threshold=threshold)


def speech_to_nonspeech(
    source: Path,
    duration: float,
    ffmpeg: str,
    work_dir: Path,
    *,
    threshold: float = 0.5,
    cancel_cb: CancelCallback | None = None,
) -> list[tuple[float, float]]:
    """Return intervals where VAD sees no speech.

    Non-speech is deliberately not called silence: the processor intersects
    these intervals with actual low-level audio before removing anything.
    """
    speech = speech_ranges(source, ffmpeg, work_dir, threshold=threshold, cancel_cb=cancel_cb)
    non_speech: list[tuple[float, float]] = []
    cursor = 0.0
    for start, end in speech:
        if start > cursor:
            non_speech.append((cursor, start))
        cursor = max(cursor, end)
    if duration > cursor:
        non_speech.append((cursor, duration))
    return non_speech


def intersect_intervals(
    a: list[tuple[float, float]],
    b: list[tuple[float, float]],
    *,
    min_duration: float = 0.0,
) -> list[tuple[float, float]]:
    """Return pairwise overlap of two sorted/unsorted interval collections."""
    aa = sorted((s, e) for s, e in a if e > s)
    bb = sorted((s, e) for s, e in b if e > s)
    out: list[tuple[float, float]] = []
    i = j = 0
    while i < len(aa) and j < len(bb):
        start = max(aa[i][0], bb[j][0])
        end = min(aa[i][1], bb[j][1])
        if end - start >= min_duration:
            out.append((start, end))
        if aa[i][1] <= bb[j][1]:
            i += 1
        else:
            j += 1
    return out


# Backwards-compatible name retained for older imports. It now accurately
# means non-speech, not acoustic silence.
def speech_to_silences(
    source: Path,
    duration: float,
    ffmpeg: str,
    work_dir: Path,
    threshold: float = 0.5,
) -> list[tuple[float, float]]:
    return speech_to_nonspeech(source, duration, ffmpeg, work_dir, threshold=threshold)
