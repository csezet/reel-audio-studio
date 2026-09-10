# Reel Audio Studio — Glass UI v5 Borderless

**v5 visual fix:** removed the 10 px transparent outer gutter and the Qt drop-shadow that combined into a thick grey frame around the app. The glass shell now reaches the actual frameless window edge; resizing still works through invisible 6 px system-resize hit zones.

Native Windows/PC desktop application for local audio enhancement of Reels/Shorts. The UI uses **Qt Widgets / PySide6**, not a browser, Electron or WebView UI.

The current interface is a **frameless semi-transparent gray desktop redesign** based on the supplied reference: custom Windows-style caption buttons, rounded glass shell, translucent processing cards, responsive six-card layout, vector line icons, waveform workspace, Auto Enhance action, and a dedicated export panel.

## What works in this MVP

- Open MP4, MOV, MKV, AVI, WebM, WAV, MP3, M4A, FLAC and AAC.
- Native drag & drop and Windows file dialogs.
- Custom frameless title bar with working minimize, maximize/restore, close, double-click maximize, native system move and edge/corner resize.
- On Windows 11 22H2+ the app requests the official DWM **Desktop Acrylic** system backdrop; older Windows versions keep a Qt semi-transparent matte fallback.
- Persistent Recent Files menu.
- Consistent programmatically drawn vector icons, including the EXE/taskbar app icon.
- Local waveform preview with playback cursor and Before/After playback.
- FFmpeg-based high-pass filtering, FFT noise reduction, voice-presence EQ, compression, optional EBU R128 loudness normalization and limiting.
- Optional removal of long pauses while cutting **video and audio together**, so sync is preserved.
- Optional **DeepFilterNet** speech enhancement when its CLI is installed.
- Optional **Silero VAD** speech detection for smarter pause removal when the package is installed.
- Export enhanced video to MP4 or audio to M4A.

## 1. Install FFmpeg

The program needs `ffmpeg` and `ffprobe`.

Either:

1. Install FFmpeg and add both executables to Windows PATH, or
2. Put `ffmpeg.exe` and `ffprobe.exe` in the project's `bin` folder.

The source archive intentionally does **not** include third-party FFmpeg binaries.

## 2. Run on Windows

Double-click:

```bat
run_windows.bat
```

It creates a local `.venv`, installs PySide6 and starts the desktop application.

Manual launch:

```bat
py -3 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## 3. Optional AI

After the base app runs:

```bat
install_ai_windows.bat
```

or manually:

```bat
pip install -r requirements-ai.txt
```

DeepFilterNet is deliberately optional because it adds a much heavier PyTorch/model dependency. Without it, Noise Removal still works using FFmpeg `afftdn`.

If Silero is not installed, pause detection automatically falls back to FFmpeg `silencedetect`.

## 4. Build an .exe folder

First put `ffmpeg.exe` and `ffprobe.exe` in `bin` if you want them shipped alongside the application. Then run:

```bat
build_windows.bat
```

Output:

```text
dist\ReelAudioStudio\ReelAudioStudio.exe
```

The build script also embeds `assets\reel_audio.ico` as the Windows executable icon and ships the UI assets folder.

This uses a PyInstaller **onedir** build instead of one giant executable, which is better suited to large native/AI dependencies.

## Current processing chain

```text
Input Reel
   |
   +-- optional Silero VAD / FFmpeg silencedetect
   |      -> synchronized video+audio pause cuts
   |
   +-- optional DeepFilterNet
   |
   +-- highpass 70 Hz
   +-- FFmpeg afftdn (when DeepFilterNet is off)
   +-- voice presence EQ around 3 kHz
   +-- FFmpeg acompressor
   +-- optional FFmpeg loudnorm (target selectable: -16/-14/-12 LUFS)
   +-- 48 kHz resample
   +-- FFmpeg alimiter
   |
Final MP4 / M4A
```

## Important MVP limitations

- The current `Voice + Music` preset does not yet separate stems. It applies conservative voice-oriented processing only. A stem-separation module should be added in the next milestone.
- Pause removal re-encodes video with H.264 because the timeline changes. Processing without pause removal copies the video stream and only re-encodes audio.
- Loudness normalization can be toggled in the UI and is currently single-pass. FFmpeg supports double-pass normalization; that should be the next mastering upgrade.
- The Music Ducking card is intentionally disabled until real voice/music stem separation is connected; the UI does not pretend an unavailable DSP stage is working.
- I have not bundled AI weights or tested every Windows GPU configuration in this archive.

## Tests

The pure processing-graph tests do not need PySide6:

```bat
python -m unittest discover -s tests -v
```


## Glass / title-bar implementation

The window itself remains a native Qt Widgets application. It uses `Qt::FramelessWindowHint` only to replace the default title bar with the reference-style one. Moving and resizing call Qt's native `QWindow::startSystemMove()` / `startSystemResize()`, so the operating system still owns the actual move/resize interaction.

On Windows 11 build 22621+ `reel_audio/ui/windows_effects.py` calls the documented DWM `DWMWA_SYSTEMBACKDROP_TYPE` attribute with `DWMSBT_TRANSIENTWINDOW` (Desktop Acrylic), requests dark non-client rendering, and opts into rounded corners. No browser, Electron, WebView, or HTML/CSS renderer is used.

Official references:

- Microsoft `DWM_SYSTEMBACKDROP_TYPE`: https://learn.microsoft.com/windows/win32/api/dwmapi/ne-dwmapi-dwm_systembackdrop_type
- Microsoft `DWMWINDOWATTRIBUTE`: https://learn.microsoft.com/windows/win32/api/dwmapi/ne-dwmapi-dwmwindowattribute
- Qt `QWindow::startSystemMove/startSystemResize`: https://doc.qt.io/qt-6/qwindow.html
- Qt window flags (`FramelessWindowHint`): https://doc.qt.io/qt-6/qt.html

### Glass UI v4

This revision fixes the slider blocks seen on some Windows systems and makes the window materially more transparent. The timeline, volume, noise, voice, compression and ducking sliders are now custom-painted instead of relying on QSS `QSlider::sub-page`. On Windows 11 22H2+ the app requests Desktop Acrylic for the whole window and extends the DWM frame across the client area; if Windows does not provide that material, the Qt alpha-transparent fallback remains active.