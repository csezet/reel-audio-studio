# Third-party components

This source archive does not bundle FFmpeg binaries or AI assets by default.

- **Qt for Python / PySide6 6.11.2** — Qt Python bindings. LGPLv3/GPLv3 or commercial Qt licensing, depending on your distribution model. https://doc.qt.io/qtforpython-6/
- **FFmpeg** — audio/video decode, filtering and encoding. FFmpeg's effective license depends on its exact build configuration. In particular, builds with GPL components such as libx264 have different redistribution obligations. https://ffmpeg.org/legal.html
- **Silero VAD v6.2.1** — MIT licensed upstream project. Reel Audio Studio uses the ONNX export through ONNX Runtime and pins the model SHA-256. https://github.com/snakers4/silero-vad
- **ONNX Runtime 1.29.0** — runtime used for the optional Silero ONNX path. https://onnxruntime.ai/
- **DeepFilterNet v0.5.6** — optional speech enhancement. On Windows Reel Audio Studio prefers the upstream precompiled `deep-filter` release executable, avoiding a required Python/PyTorch backend. https://github.com/Rikorose/DeepFilterNet
- **PyInstaller 6.22.2** — development/build dependency used to make the Windows onedir bundle. https://pyinstaller.org/

Before commercial distribution, freeze the exact third-party binaries/assets you ship, retain required notices, and review their licenses. Do not substitute an arbitrary FFmpeg binary without checking its configuration and license.
