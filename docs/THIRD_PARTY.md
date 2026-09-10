# Third-party components

This source tree does not bundle FFmpeg binaries or AI model weights.

- **Qt for Python / PySide6** — official Qt Python bindings. Licensing: LGPLv3/GPLv3 or Qt commercial license. https://doc.qt.io/qtforpython-6/
- **FFmpeg** — audio/video processing engine. License depends on the exact build configuration. https://ffmpeg.org/legal.html
- **DeepFilterNet** — optional speech enhancement/noise suppression integration. Repository: https://github.com/Rikorose/DeepFilterNet
- **Silero VAD** — optional voice activity detection integration. Repository: https://github.com/snakers4/silero-vad

Before commercial distribution, review and freeze the licenses of the exact FFmpeg build, Python wheels and model weights you ship.
