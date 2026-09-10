from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from reel_audio.engine.processor import AudioProcessor, ProcessingSettings
from reel_audio.engine.waveform import waveform_peaks


class ProcessingThread(QThread):
    stage = Signal(str)
    done = Signal(str)
    failed = Signal(str)

    def __init__(self, input_path: str, output_path: str, settings: ProcessingSettings, parent=None):
        super().__init__(parent)
        self.input_path = input_path
        self.output_path = output_path
        self.settings = settings

    def run(self):
        try:
            out = AudioProcessor().process(
                self.input_path,
                self.output_path,
                self.settings,
                status_cb=self.stage.emit,
            )
            self.done.emit(str(out))
        except Exception as exc:
            self.failed.emit(str(exc))


class WaveformThread(QThread):
    done = Signal(list)
    failed = Signal(str)

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self.path = path

    def run(self):
        try:
            self.done.emit(waveform_peaks(self.path))
        except Exception as exc:
            self.failed.emit(str(exc))
