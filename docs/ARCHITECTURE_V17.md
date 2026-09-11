# Architecture v17

## Goals

v17 turns the earlier visual MVP into a safer desktop processing pipeline. The main rule is that the UI never owns long-running FFmpeg work directly and no destructive output is committed until the operation completes.

## Threading

`ProcessingThread`, `ExportThread` and `WaveformThread` are `QThread` workers. `requestInterruption()` is passed down as a cooperative cancellation callback. FFmpeg child processes are terminated and then killed if they do not exit promptly.

Waveform jobs carry a monotonically increasing request ID. A late result from an older file is ignored even if the OS schedules it after a newer request.

## FFmpeg process runner

`engine/tools.py` owns command execution. For FFmpeg operations with progress enabled it injects `-progress pipe:1 -nostats`, converts output timestamps to 0–100%, and drains stderr on a separate thread.

The runner also centralizes executable lookup, including PyInstaller's resource directory and the application directory.

## Pause removal

Silero VAD is never treated as a silence detector.

```text
acoustic silence (FFmpeg) ∩ non-speech (Silero) = removable region
```

Without Silero, only acoustic silence is considered. The resulting keep segments are applied to video and audio together via the concat filter so sync is preserved.

## Silero VAD runtime

The VAD path is intentionally PyTorch-free:

1. FFmpeg decodes mono 16 kHz float32 PCM.
2. Audio is streamed in 512-sample frames.
3. The wrapper preserves Silero's recurrent state and 64-sample context.
4. ONNX Runtime returns speech probabilities.
5. A hysteresis/post-processing stage converts them into protected speech ranges.

The pinned model is Silero v6.2.1. The installer verifies its SHA-256 before committing it.

## Loudness / limiting

When normalization is enabled:

1. The preset DSP preceding mastering is applied in the first measurement pass.
2. `loudnorm` JSON is parsed for measured integrated loudness, LRA, true peak, threshold and target offset.
3. Those values are supplied to the second pass.
4. Audio is resampled to 48 kHz.
5. `alimiter` uses a linear limit of `0.8414` (approximately −1.5 dBFS), with auto-level disabled.

If first-pass JSON is unavailable, the engine falls back to a safe single-pass loudnorm rather than aborting the project.

## Voice + Music

Until stem separation exists, the preset uses conservative full-mix processing. Speech-only denoising/presence EQ and DeepFilterNet are skipped to avoid damaging music.

## Export safety

Exports are written to a temporary file in the destination directory and committed with `os.replace`. Direct copies are chunked and cancellable. Wrong filename suffixes are normalized to the selected format.

Video encoders are discovered from the local FFmpeg build. Windows Media Foundation H.264 is preferred on Windows; `libx264` is never assumed to exist.

## Build / resources

PyInstaller's `.spec` file is checked into source. Bundle data are resolved using `_MEIPASS` while writable user data stay outside the bundle.

`build_windows_ai.bat` installs ONNX Runtime, downloads/verifies Silero and downloads the official DeepFilterNet native Windows binary before building.

## Diagnostics

A rotating diagnostic log lives under the current user's local application data directory. Command failures and media-player errors are recorded without making logging a startup dependency.
