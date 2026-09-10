from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget


class WaveformWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._peaks: list[float] = []
        self._progress = 0.0
        self._duration_ms = 0
        self.setMinimumHeight(118)

    def set_peaks(self, peaks: list[float]) -> None:
        self._peaks = peaks
        self.update()

    def set_progress(self, value: float) -> None:
        self._progress = min(1.0, max(0.0, float(value)))
        self.update()

    def set_duration(self, duration_ms: int) -> None:
        self._duration_ms = max(0, int(duration_ms))
        self.update()

    @staticmethod
    def _fmt(ms: int) -> str:
        sec = max(0, ms // 1000)
        return f"{sec // 60:02d}:{sec % 60:02d}"

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        bg = self.rect().adjusted(0, 0, -1, -1)
        painter.setPen(QPen(QColor(188, 204, 217, 24), 1))
        painter.setBrush(QColor(11, 17, 23, 82))
        painter.drawRoundedRect(bg, 8, 8)

        rect = self.rect().adjusted(10, 7, -10, -22)
        painter.setPen(QPen(QColor(140, 157, 171, 26), 1))
        for i in range(1, 8):
            x = rect.left() + int(rect.width() * i / 8)
            painter.drawLine(x, rect.top(), x, rect.bottom())
        painter.setPen(QPen(QColor(166, 181, 194, 35), 1))
        painter.drawLine(rect.left(), rect.center().y(), rect.right(), rect.center().y())

        if not self._peaks:
            painter.setPen(QColor(135, 149, 161, 160))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "Waveform появится после выбора файла")
        else:
            center = rect.center().y()
            half = max(1, rect.height() // 2 - 4)
            count = len(self._peaks)
            progress_x = rect.left() + int(rect.width() * self._progress)
            path_before = QPainterPath(); path_after = QPainterPath()
            first_before = first_after = True
            for x in range(max(1, rect.width())):
                idx = min(count - 1, int(x * count / max(1, rect.width())))
                amp = min(1.0, max(0.0, self._peaks[idx]))
                h = max(1, int(amp * half))
                px = rect.left() + x
                target = path_before if px <= progress_x else path_after
                if (px <= progress_x and first_before) or (px > progress_x and first_after):
                    target.moveTo(px, center - h)
                    if px <= progress_x: first_before = False
                    else: first_after = False
                target.lineTo(px, center - h)
            # Draw bars instead of a filled blob to preserve audio detail at any width.
            for x in range(max(1, rect.width())):
                idx = min(count - 1, int(x * count / max(1, rect.width())))
                amp = min(1.0, max(0.0, self._peaks[idx]))
                h = max(1, int(amp * half))
                px = rect.left() + x
                color = QColor(188, 202, 214, 205) if px <= progress_x else QColor(112, 128, 142, 180)
                painter.setPen(QPen(color, 1))
                painter.drawLine(px, center - h, px, center + h)
            painter.setPen(QPen(QColor(228, 235, 241, 225), 1.5))
            painter.drawLine(progress_x, rect.top(), progress_x, rect.bottom())
            painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(QColor(230, 237, 242, 240))
            painter.drawEllipse(QRectF(progress_x - 4, rect.top() - 3, 8, 8))

        # Time ruler.
        painter.setPen(QColor(139, 153, 165, 175))
        y = self.height() - 6
        ticks = 6
        for i in range(ticks):
            x = 10 + int((self.width() - 20) * i / (ticks - 1))
            ms = int(self._duration_ms * i / (ticks - 1)) if self._duration_ms else 0
            text = self._fmt(ms)
            align = Qt.AlignmentFlag.AlignLeft if i == 0 else (Qt.AlignmentFlag.AlignRight if i == ticks - 1 else Qt.AlignmentFlag.AlignHCenter)
            box = QRectF(x - 25, y - 14, 50, 14)
            if i == 0: box.moveLeft(10)
            if i == ticks - 1: box.moveRight(self.width() - 10)
            painter.drawText(box, align | Qt.AlignmentFlag.AlignVCenter, text)
