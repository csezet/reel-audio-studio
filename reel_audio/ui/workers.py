from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from reel_audio.engine.exporter import export_media
from reel_audio.engine.processor import AudioProcessor, ProcessingSettings
from reel_audio.engine.tools import CommandCancelled, media_summary
from reel_audio.engine.waveform import waveform_peaks


class ProcessingThread(QThread):
    stage = Signal(str)
    progress = Signal(int)
    done = Signal(str)
    failed = Signal(str)
    cancelled = Signal()

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
                progress_cb=self.progress.emit,
                cancel_cb=self.isInterruptionRequested,
            )
            if self.isInterruptionRequested():
                self.cancelled.emit()
            else:
                self.done.emit(str(out))
        except CommandCancelled:
            self.cancelled.emit()
        except Exception as exc:
            self.failed.emit(str(exc))


class ExportThread(QThread):
    stage = Signal(str)
    progress = Signal(int)
    done = Signal(str)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, source: str, destination: str, format_name: str, quality: str, parent=None):
        super().__init__(parent)
        self.source = source
        self.destination = destination
        self.format_name = format_name
        self.quality = quality

    def run(self):
        try:
            out = export_media(
                self.source,
                self.destination,
                format_name=self.format_name,
                quality=self.quality,
                status_cb=self.stage.emit,
                progress_cb=self.progress.emit,
                cancel_cb=self.isInterruptionRequested,
            )
            if self.isInterruptionRequested():
                self.cancelled.emit()
            else:
                self.done.emit(str(out))
        except CommandCancelled:
            self.cancelled.emit()
        except Exception as exc:
            self.failed.emit(str(exc))


class WaveformThread(QThread):
    done = Signal(int, list)
    failed = Signal(int, str)

    def __init__(self, path: str, request_id: int, duration: float | None = None, parent=None):
        super().__init__(parent)
        self.path = path
        self.request_id = request_id
        self.duration = duration

    def run(self):
        try:
            duration = self.duration
            if not duration:
                try:
                    duration = float(media_summary(self.path, cancel_cb=self.isInterruptionRequested).get("duration") or 0.0)
                except Exception:
                    duration = None
            peaks = waveform_peaks(
                self.path,
                duration=duration,
                cancel_cb=self.isInterruptionRequested,
            )
            if not self.isInterruptionRequested():
                self.done.emit(self.request_id, peaks)
        except CommandCancelled:
            return
        except Exception as exc:
            if not self.isInterruptionRequested():
                self.failed.emit(self.request_id, str(exc))
