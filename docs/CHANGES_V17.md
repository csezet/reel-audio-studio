# v17 changes

- cancellable FFmpeg/process/export/waveform jobs with real progress
- request-safe incremental waveform generation
- two-pass EBU R128 loudnorm
- corrected limiter auto-level behavior and −1.5 dBFS linear ceiling
- safe pause removal: acoustic silence intersected with VAD non-speech
- PyTorch-free Silero ONNX runtime path with pinned model hash
- native Windows DeepFilterNet release asset support
- stereo-preserving DeepFilter input and Voice+Music safeguards
- dynamic encoder discovery instead of mandatory libx264
- explicit MP4/M4A/WAV export, atomic destination commit, cancellable copy
- rotating diagnostics log and QMediaPlayer error reporting
- High-DPI rounding policy
- PyInstaller resource-root fix for `_MEIPASS`/`_internal`
- refactored UI modules and reproducible spec/requirements
- 16 unit tests plus a real FFmpeg end-to-end verification during development
