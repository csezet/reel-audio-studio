from __future__ import annotations

import importlib
import shutil
import sys
import tempfile
import uuid
from pathlib import Path

from PySide6.QtCore import QEvent, QEasingCurve, Property, QProcess, QPropertyAnimation, QRectF, QSettings, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QFont, QIcon, QLinearGradient, QMouseEvent, QPainter, QPainterPath, QPalette, QPen
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QButtonGroup,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListView,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from reel_audio.engine.deepfilter import deepfilter_available
from reel_audio.engine.processor import ProcessingSettings
from reel_audio.engine.tools import find_executable, media_summary
from reel_audio.engine.vad import silero_available
from .vector_icons import draw_vector_icon, make_icon, make_state_icon
from .waveform_widget import WaveformWidget
from .windows_effects import (
    SW_MAXIMIZE, SW_MINIMIZE, SW_RESTORE,
    apply_windows_backdrop, enable_native_window_animations,
    is_nccalcsize_message, show_window_native,
)
from .workers import ProcessingThread, WaveformThread

SUPPORTED = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".wav", ".mp3", ".m4a", ".flac", ".aac"}


def ui_animations_enabled() -> bool:
    value = QSettings("ReelAudioStudio", "ReelAudioStudio").value("ui_animations", True)
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off"}
    return bool(value)


class GlassShell(QFrame):
    """The single translucent window plate, painted strictly inside its own rect.

    The top-level window remains alpha-transparent.  This widget paints the
    semi-transparent grey glass surface with a rounded QPainterPath, so no
    shadow, margin or backdrop can extend past the native window bounds.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("GlassShell")
        self.setAutoFillBackground(False)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        maximized = bool(self.property("maximized"))
        radius = 0.0 if maximized else 16.0
        # Keep antialiased border fully inside the widget rectangle.
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        if radius > 0:
            path.addRoundedRect(rect, radius, radius)
        else:
            path.addRect(rect)

        painter.setClipPath(path)
        gradient = QLinearGradient(0.0, rect.top(), 0.0, rect.bottom())
        # Semi-transparent grey glass: the desktop remains visible through it,
        # but the entire application keeps one coherent background plate.
        # Soft glass: only a small amount of the desktop should show through.
        # Keep opacity on the background plate itself (rather than windowOpacity)
        # so text, icons and controls remain fully crisp and opaque.
        # v10: denser glass.  Keep only a subtle hint of the desktop visible.
        # Alpha is intentionally changed only on the background plate, not on
        # the entire window, so text/icons/controls stay fully opaque and crisp.
        gradient.setColorAt(0.0, QColor(55, 66, 77, 246))
        gradient.setColorAt(0.52, QColor(37, 46, 55, 243))
        gradient.setColorAt(1.0, QColor(27, 35, 42, 245))
        painter.fillPath(path, gradient)

        if not maximized:
            painter.setClipping(False)
            painter.setPen(QPen(QColor(213, 224, 233, 46), 1.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)


class ToggleSwitch(QAbstractButton):
    """Animated Windows-11-like toggle.

    The knob position is a real Qt property so QPropertyAnimation can move it
    smoothly instead of jumping between the two ends of the track.
    """

    def __init__(self, checked: bool = True, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(42, 23)
        self._position = 1.0 if checked else 0.0
        self._anim = QPropertyAnimation(self, b"position", self)
        self._anim.setDuration(145)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate_toggle)

    def sizeHint(self) -> QSize:
        return QSize(42, 23)

    def _get_position(self) -> float:
        return self._position

    def _set_position(self, value: float) -> None:
        self._position = max(0.0, min(1.0, float(value)))
        self.update()

    position = Property(float, _get_position, _set_position)

    def _animate_toggle(self, checked: bool) -> None:
        target = 1.0 if checked else 0.0
        if not ui_animations_enabled():
            self._set_position(target)
            return
        self._anim.stop()
        self._anim.setStartValue(self._position)
        self._anim.setEndValue(target)
        self._anim.start()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(0.7, 0.7, self.width() - 1.4, self.height() - 1.4)
        if not self.isEnabled():
            track, knob = QColor(70, 77, 85, 115), QColor(137, 145, 153, 130)
        elif self.isChecked():
            track, knob = QColor(219, 226, 232, 230), QColor(69, 77, 85, 245)
        else:
            track, knob = QColor(93, 101, 110, 175), QColor(211, 217, 223, 220)
        painter.setPen(QPen(QColor(255, 255, 255, 28), 1))
        painter.setBrush(track)
        painter.drawRoundedRect(rect, 11, 11)
        diameter = 17.0
        left_x = 3.0
        right_x = self.width() - diameter - 3.0
        x = left_x + (right_x - left_x) * self._position
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(knob)
        painter.drawEllipse(QRectF(x, 3.0, diameter, diameter))


class GlassSlider(QSlider):
    """Small custom-painted slider used to avoid native/QSS fill artifacts on Windows.

    Qt's platform slider and QSS sub-page rendering can produce chunky rectangular
    fills at some DPI/scaling combinations.  This widget paints the groove, progress
    and handle itself while keeping QSlider's value/signals API.
    """

    def __init__(self, orientation=Qt.Orientation.Horizontal, *, track_height: int = 4, handle_diameter: int = 13, parent=None):
        super().__init__(orientation, parent)
        self._track_height = track_height
        self._handle_diameter = handle_diameter
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if orientation == Qt.Orientation.Horizontal:
            self.setMinimumHeight(max(18, handle_diameter + 6))
        self.valueChanged.connect(lambda _v: self.update())
        self.rangeChanged.connect(lambda _a, _b: self.update())

    def _ratio(self) -> float:
        span = self.maximum() - self.minimum()
        return 0.0 if span <= 0 else (self.value() - self.minimum()) / span

    def _value_from_pos(self, pos: float) -> int:
        if self.orientation() == Qt.Orientation.Horizontal:
            usable = max(1.0, self.width() - self._handle_diameter)
            r = (pos - self._handle_diameter / 2.0) / usable
        else:
            usable = max(1.0, self.height() - self._handle_diameter)
            r = 1.0 - ((pos - self._handle_diameter / 2.0) / usable)
        r = max(0.0, min(1.0, r))
        return round(self.minimum() + r * (self.maximum() - self.minimum()))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        enabled = self.isEnabled()
        d = float(self._handle_diameter)
        ratio = self._ratio()

        if self.orientation() == Qt.Orientation.Horizontal:
            left = d / 2.0
            right = self.width() - d / 2.0
            cy = self.height() / 2.0
            track = QRectF(left, cy - self._track_height / 2.0, max(1.0, right - left), self._track_height)
            px = left + track.width() * ratio
            progress = QRectF(track.left(), track.top(), max(0.0, px - track.left()), track.height())
            knob = QRectF(px - d / 2.0, cy - d / 2.0, d, d)
        else:
            top = d / 2.0
            bottom = self.height() - d / 2.0
            cx = self.width() / 2.0
            track = QRectF(cx - self._track_height / 2.0, top, self._track_height, max(1.0, bottom - top))
            py = bottom - track.height() * ratio
            progress = QRectF(track.left(), py, track.width(), max(0.0, bottom - py))
            knob = QRectF(cx - d / 2.0, py - d / 2.0, d, d)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(171, 184, 196, 45 if enabled else 24))
        p.drawRoundedRect(track, self._track_height / 2.0, self._track_height / 2.0)
        if progress.width() > 0 and progress.height() > 0:
            p.setBrush(QColor(206, 216, 224, 132 if enabled else 48))
            p.drawRoundedRect(progress, self._track_height / 2.0, self._track_height / 2.0)

        p.setPen(QPen(QColor(255, 255, 255, 78 if enabled else 26), 1))
        p.setBrush(QColor(224, 231, 236, 235 if enabled else 90))
        p.drawEllipse(knob)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self.setSliderDown(True)
            pos = event.position().x() if self.orientation() == Qt.Orientation.Horizontal else event.position().y()
            self.setValue(self._value_from_pos(pos))
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.isSliderDown() and self.isEnabled():
            pos = event.position().x() if self.orientation() == Qt.Orientation.Horizontal else event.position().y()
            self.setValue(self._value_from_pos(pos))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self.isSliderDown():
            pos = event.position().x() if self.orientation() == Qt.Orientation.Horizontal else event.position().y()
            self.setValue(self._value_from_pos(pos))
            self.setSliderDown(False)
            event.accept()
            return
        super().mouseReleaseEvent(event)


class GlassComboBox(QComboBox):
    """Combo box with a controlled glass popup and no native focus rectangle.

    Export selectors currently contain a single valid option.  For those fields
    ``lock_single`` prevents opening a one-row popup that looks like a stray
    black rectangle on Windows while keeping the control visually consistent.
    """

    def __init__(self, parent=None, *, lock_single: bool = False):
        super().__init__(parent)
        self._lock_single = lock_single
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        view = QListView(self)
        view.setObjectName("GlassComboPopup")
        view.setFrameShape(QFrame.Shape.NoFrame)
        view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        view.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        view.setSpacing(2)
        self.setView(view)

    def showPopup(self) -> None:
        if self._lock_single and self.count() <= 1:
            self.clearFocus()
            return
        super().showPopup()
        # The popup is a separate top-level container.  Make its content fully
        # controlled by our stylesheet rather than the Windows/Fusion focus UI.
        popup = self.view().window()
        if popup is not None:
            popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._lock_single and self.count() <= 1:
            event.accept()
            return
        super().mousePressEvent(event)


class IconBadge(QWidget):
    def __init__(self, icon_name: str, size: int = 52, parent=None):
        super().__init__(parent)
        self.icon_name = icon_name
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(QPen(QColor(255, 255, 255, 35), 1))
        p.setBrush(QColor(110, 122, 134, 74))
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 14, 14)
        draw_vector_icon(p, self.icon_name, QRectF(12, 12, self.width() - 24, self.height() - 24), QColor("#e7edf3"), 1.8)


class FileAddButton(QAbstractButton):
    """Clickable + tile that opens the same file picker as the main Open button.

    Older builds used :class:`IconBadge` here.  IconBadge deliberately ignores
    mouse events, so the tile looked interactive but could never be clicked.
    This control keeps the same visual language while behaving as a real button.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(50, 50)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setToolTip("Выбрать видео или аудио")
        self.setAccessibleName("Выбрать видео или аудио")
        self._hover_progress = 0.0
        self._hover_anim = QPropertyAnimation(self, b"hoverProgress", self)
        self._hover_anim.setDuration(145)
        self._hover_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _get_hover_progress(self) -> float:
        return self._hover_progress

    def _set_hover_progress(self, value: float) -> None:
        self._hover_progress = max(0.0, min(1.0, float(value)))
        self.update()

    hoverProgress = Property(float, _get_hover_progress, _set_hover_progress)

    def _animate_hover(self, target: float) -> None:
        if not ui_animations_enabled():
            self._set_hover_progress(target)
            return
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_progress)
        self._hover_anim.setEndValue(target)
        self._hover_anim.start()

    def enterEvent(self, event):
        self._animate_hover(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._animate_hover(0.0)
        super().leaveEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        hover = self._hover_progress
        pressed = 1.0 if self.isDown() else 0.0
        base_alpha = 74 + int(hover * 34)
        if pressed:
            base_alpha = 125

        rect = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
        border_alpha = 35 + int(hover * 45)
        p.setPen(QPen(QColor(255, 255, 255, border_alpha), 1.0))
        p.setBrush(QColor(110, 122, 134, base_alpha))
        p.drawRoundedRect(rect, 14, 14)

        # Subtle inner highlight makes the tile read as a button without
        # introducing a hard rectangular Windows hover background.
        if hover > 0.001 and not pressed:
            glow = QRectF(rect).adjusted(2.0, 2.0, -2.0, -2.0)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(235, 242, 247, int(hover * 12)))
            p.drawRoundedRect(glow, 12, 12)

        icon_color = QColor(247, 250, 252) if (hover > 0.35 or pressed) else QColor("#e7edf3")
        draw_vector_icon(p, "plus", QRectF(12, 12, self.width() - 24, self.height() - 24), icon_color, 1.9)


class CaptionButton(QAbstractButton):
    """Compact Windows-11-like caption control with an inset rounded backplate.

    The previous implementation used ``fillRect(self.rect())`` for hover states.
    On a frameless title bar that produced conspicuous square blocks.  This
    version paints the hover/pressed material inside the button bounds and
    fades it in/out, so the controls visually belong to the rounded glass shell.
    """

    def __init__(self, kind: str, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.setFixedSize(40, 32)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._hover_progress = 0.0
        self._hover_anim = QPropertyAnimation(self, b"hoverProgress", self)
        self._hover_anim.setDuration(125)
        self._hover_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _get_hover_progress(self) -> float:
        return self._hover_progress

    def _set_hover_progress(self, value: float) -> None:
        self._hover_progress = max(0.0, min(1.0, float(value)))
        self.update()

    hoverProgress = Property(float, _get_hover_progress, _set_hover_progress)

    def _animate_hover(self, target: float) -> None:
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_progress)
        self._hover_anim.setEndValue(target)
        if ui_animations_enabled():
            self._hover_anim.start()
        else:
            self._set_hover_progress(target)

    def enterEvent(self, event):
        self._animate_hover(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._animate_hover(0.0)
        super().leaveEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        hover = self._hover_progress
        pressed = self.isDown()
        plate = QRectF(self.rect()).adjusted(3.0, 2.0, -3.0, -2.0)
        radius = 7.0

        p.setPen(Qt.PenStyle.NoPen)
        if self.kind == "close":
            # Red is reserved for the destructive close action, but unlike the
            # old full-cell rectangle it stays inset and follows the UI radius.
            alpha = int((210 if not pressed else 238) * hover)
            if alpha:
                p.setBrush(QColor(196, 55, 66, alpha))
                p.drawRoundedRect(plate, radius, radius)
        else:
            alpha = int((22 if not pressed else 34) * hover)
            if alpha:
                p.setBrush(QColor(255, 255, 255, alpha))
                p.drawRoundedRect(plate, radius, radius)

        icon_color = QColor("#ffffff") if self.kind == "close" and hover > 0.22 else QColor("#dce3e9")
        pen = QPen(icon_color, 1.2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        cx, cy = self.width() / 2.0, self.height() / 2.0

        if self.kind == "min":
            p.drawLine(cx - 4.5, cy + 1.5, cx + 4.5, cy + 1.5)
        elif self.kind == "max":
            window = self.window()
            if hasattr(window, "isMaximized") and window.isMaximized():
                # Restore glyph: two softly rounded overlapping outlines.
                p.drawRoundedRect(QRectF(cx - 3.8, cy - 2.8, 7.6, 6.6), 1.1, 1.1)
                p.drawRoundedRect(QRectF(cx - 1.8, cy - 4.8, 7.6, 6.6), 1.1, 1.1)
            else:
                p.drawRoundedRect(QRectF(cx - 4.2, cy - 4.2, 8.4, 8.4), 1.2, 1.2)
        else:
            p.drawLine(cx - 4.0, cy - 4.0, cx + 4.0, cy + 4.0)
            p.drawLine(cx + 4.0, cy - 4.0, cx - 4.0, cy + 4.0)


class TitleBar(QWidget):
    def __init__(self, window: "MainWindow"):
        super().__init__(window)
        self.owner = window
        self.setObjectName("TitleBar")
        self.setFixedHeight(64)

        row = QHBoxLayout(self)
        row.setContentsMargins(18, 8, 8, 5)
        row.setSpacing(12)
        badge = IconBadge("waveform", 48)
        row.addWidget(badge)

        texts = QVBoxLayout()
        texts.setSpacing(1)
        title = QLabel("R E E L   A U D I O   S T U D I O")
        title.setObjectName("Title")
        subtitle = QLabel("ЧИСТЫЙ ЗВУК ДЛЯ ВАШИХ REELS")
        subtitle.setObjectName("Subtitle")
        title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        subtitle.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        texts.addStretch(1); texts.addWidget(title); texts.addWidget(subtitle); texts.addStretch(1)
        row.addLayout(texts)
        row.addStretch(1)

        self.settings_btn = QPushButton("Настройки")
        self.settings_btn.setObjectName("TitleGhostButton")
        self.settings_btn.setIcon(make_icon("settings", "#c4ccd4"))
        self.settings_btn.setIconSize(QSize(18, 18))
        self.settings_btn.clicked.connect(window.show_settings)
        row.addWidget(self.settings_btn)

        controls = QHBoxLayout(); controls.setSpacing(1); controls.setContentsMargins(5, 0, 0, 0)
        self.min_btn = CaptionButton("min")
        self.max_btn = CaptionButton("max")
        self.close_btn = CaptionButton("close")
        self.min_btn.clicked.connect(window.minimize_window)
        self.max_btn.clicked.connect(window.toggle_maximize)
        self.close_btn.clicked.connect(window.close)
        controls.addWidget(self.min_btn); controls.addWidget(self.max_btn); controls.addWidget(self.close_btn)
        row.addLayout(controls)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and not self.owner.isMaximized():
            wh = self.owner.windowHandle()
            if wh and wh.startSystemMove():
                event.accept(); return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.owner.toggle_maximize(); event.accept(); return
        super().mouseDoubleClickEvent(event)


class ResizeHandle(QWidget):
    def __init__(self, owner: "MainWindow", edges: Qt.Edge, cursor: Qt.CursorShape):
        super().__init__(owner)
        self.owner = owner
        self.edges = edges
        self.setCursor(cursor)
        self.setStyleSheet("background: transparent;")

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and not self.owner.isMaximized():
            wh = self.owner.windowHandle()
            if wh:
                wh.startSystemResize(self.edges)
                event.accept(); return
        super().mousePressEvent(event)


class DropFrame(QFrame):
    def __init__(self, on_file, parent=None):
        super().__init__(parent)
        self.on_file = on_file
        self.setAcceptDrops(True)
        self.setObjectName("DropFrame")

    def dragEnterEvent(self, event):
        urls = event.mimeData().urls()
        if urls and Path(urls[0].toLocalFile()).suffix.lower() in SUPPORTED:
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            self.on_file(urls[0].toLocalFile())
            event.acceptProposedAction()


class AnimatedPresetButton(QPushButton):
    """Preset tile with smooth hover and selected-state transitions."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._hover_progress = 0.0
        self._select_progress = 1.0 if self.isChecked() else 0.0
        self._hover_anim = QPropertyAnimation(self, b"hoverProgress", self)
        self._hover_anim.setDuration(165)
        self._hover_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._select_anim = QPropertyAnimation(self, b"selectProgress", self)
        self._select_anim.setDuration(190)
        self._select_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.toggled.connect(self._animate_selected)

    @staticmethod
    def _mix(a: QColor, b: QColor, t: float) -> QColor:
        t = max(0.0, min(1.0, t))
        return QColor(
            round(a.red() + (b.red() - a.red()) * t),
            round(a.green() + (b.green() - a.green()) * t),
            round(a.blue() + (b.blue() - a.blue()) * t),
            round(a.alpha() + (b.alpha() - a.alpha()) * t),
        )

    def _get_hover_progress(self) -> float:
        return self._hover_progress

    def _set_hover_progress(self, value: float) -> None:
        self._hover_progress = max(0.0, min(1.0, float(value)))
        self.update()

    hoverProgress = Property(float, _get_hover_progress, _set_hover_progress)

    def _get_select_progress(self) -> float:
        return self._select_progress

    def _set_select_progress(self, value: float) -> None:
        self._select_progress = max(0.0, min(1.0, float(value)))
        self.update()

    selectProgress = Property(float, _get_select_progress, _set_select_progress)

    def _animate_hover(self, target: float) -> None:
        if not ui_animations_enabled():
            self._set_hover_progress(target)
            return
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_progress)
        self._hover_anim.setEndValue(target)
        self._hover_anim.start()

    def _animate_selected(self, checked: bool) -> None:
        target = 1.0 if checked else 0.0
        if not ui_animations_enabled():
            self._set_select_progress(target)
            return
        self._select_anim.stop()
        self._select_anim.setStartValue(self._select_progress)
        self._select_anim.setEndValue(target)
        self._select_anim.start()

    def enterEvent(self, event):
        self._animate_hover(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._animate_hover(0.0)
        super().leaveEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.6, 0.6, -0.6, -0.6)
        base = QColor(40, 50, 60, 70)
        selected = QColor(235, 240, 244, 232)
        fill = self._mix(base, selected, self._select_progress)
        if self._hover_progress > 0 and self._select_progress < 0.98:
            hover = QColor(78, 91, 103, 103)
            fill = self._mix(fill, hover, self._hover_progress * 0.62)
        border_a = QColor(194, 207, 219, 37)
        border_b = QColor(255, 255, 255, 240)
        border = self._mix(border_a, border_b, self._select_progress)
        if self._hover_progress > 0 and self._select_progress < 0.98:
            border = self._mix(border, QColor(226, 235, 242, 102), self._hover_progress)
        p.setPen(QPen(border, 1.0))
        p.setBrush(fill)
        p.drawRoundedRect(rect, 9.0, 9.0)
        p.end()
        super().paintEvent(event)



class AnimatedPrimaryButton(QAbstractButton):
    """Large primary action with native-painted hover/press/attention motion.

    It intentionally remains interactive before a media file is selected so the
    hover animation is always visible.  Clicking it without media produces a
    short visual attention pulse instead of silently doing nothing.
    """

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setText(text)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumWidth(610)
        self.setFixedHeight(46)
        self._hover_progress = 0.0
        self._attention_progress = 0.0

        self._hover_anim = QPropertyAnimation(self, b"hoverProgress", self)
        self._hover_anim.setDuration(170)
        self._hover_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._attention_anim = QPropertyAnimation(self, b"attentionProgress", self)
        self._attention_anim.setDuration(520)
        self._attention_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._attention_anim.setKeyValueAt(0.0, 0.0)
        self._attention_anim.setKeyValueAt(0.24, 1.0)
        self._attention_anim.setKeyValueAt(0.58, 0.35)
        self._attention_anim.setKeyValueAt(1.0, 0.0)

    @staticmethod
    def _mix(a: QColor, b: QColor, t: float) -> QColor:
        t = max(0.0, min(1.0, float(t)))
        return QColor(
            round(a.red() + (b.red() - a.red()) * t),
            round(a.green() + (b.green() - a.green()) * t),
            round(a.blue() + (b.blue() - a.blue()) * t),
            round(a.alpha() + (b.alpha() - a.alpha()) * t),
        )

    def _get_hover_progress(self) -> float:
        return self._hover_progress

    def _set_hover_progress(self, value: float) -> None:
        self._hover_progress = max(0.0, min(1.0, float(value)))
        self.update()

    hoverProgress = Property(float, _get_hover_progress, _set_hover_progress)

    def _get_attention_progress(self) -> float:
        return self._attention_progress

    def _set_attention_progress(self, value: float) -> None:
        self._attention_progress = max(0.0, min(1.0, float(value)))
        self.update()

    attentionProgress = Property(float, _get_attention_progress, _set_attention_progress)

    def _animate_hover(self, target: float) -> None:
        if not ui_animations_enabled():
            self._set_hover_progress(target)
            return
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_progress)
        self._hover_anim.setEndValue(target)
        self._hover_anim.start()

    def pulse_attention(self) -> None:
        if not ui_animations_enabled():
            self.update()
            return
        self._attention_anim.stop()
        self._attention_anim.setStartValue(0.0)
        self._attention_anim.start()

    def enterEvent(self, event):
        if self.isEnabled():
            self._animate_hover(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._animate_hover(0.0)
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        super().mousePressEvent(event)
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        super().mouseReleaseEvent(event)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = QRectF(self.rect()).adjusted(0.8, 0.8, -0.8, -0.8)
        hover = self._hover_progress if self.isEnabled() else 0.0
        attention = self._attention_progress if self.isEnabled() else 0.0
        pressed = 1.0 if self.isDown() else 0.0

        if self.isEnabled():
            top = self._mix(QColor(118, 131, 143, 214), QColor(146, 159, 171, 232), hover)
            bottom = self._mix(QColor(69, 80, 90, 222), QColor(83, 96, 107, 234), hover)
            if pressed:
                top = self._mix(top, QColor(79, 91, 101, 236), 0.48)
                bottom = self._mix(bottom, QColor(54, 64, 73, 238), 0.48)
            if attention:
                top = self._mix(top, QColor(166, 180, 191, 242), attention * 0.55)
                bottom = self._mix(bottom, QColor(94, 108, 119, 240), attention * 0.42)
            border = self._mix(QColor(225, 234, 241, 105), QColor(246, 250, 252, 188), max(hover * 0.72, attention))
            text_color = QColor(250, 252, 253)
        else:
            top = QColor(72, 80, 88, 112)
            bottom = QColor(49, 57, 64, 120)
            border = QColor(168, 178, 187, 34)
            text_color = QColor(113, 124, 134)

        grad = QLinearGradient(0.0, rect.top(), 0.0, rect.bottom())
        grad.setColorAt(0.0, top)
        grad.setColorAt(1.0, bottom)
        p.setPen(QPen(border, 1.0 + 0.5 * attention))
        p.setBrush(grad)
        p.drawRoundedRect(rect, 13.0, 13.0)

        # Small moving highlight on hover: subtle enough to read as Win11 glass,
        # not as a browser-style button effect.
        if hover > 0.02:
            shine = QLinearGradient(rect.left(), 0.0, rect.right(), 0.0)
            shine.setColorAt(0.0, QColor(255, 255, 255, 0))
            shine.setColorAt(0.48, QColor(255, 255, 255, round(22 * hover)))
            shine.setColorAt(0.62, QColor(255, 255, 255, round(7 * hover)))
            shine.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(shine)
            p.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 12.0, 12.0)

        font = self.font()
        font.setBold(True)
        font.setPointSizeF(max(font.pointSizeF(), 10.5))
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.7)
        p.setFont(font)
        fm = p.fontMetrics()
        text = self.text()
        icon_size = 21.0
        gap = 8.0
        total = icon_size + gap + fm.horizontalAdvance(text)
        x = rect.center().x() - total / 2.0
        y = rect.center().y() - icon_size / 2.0
        draw_vector_icon(p, "sparkles", QRectF(x, y, icon_size, icon_size), text_color, 1.7)
        p.setPen(text_color)
        p.drawText(QRectF(x + icon_size + gap, rect.top(), fm.horizontalAdvance(text) + 3, rect.height()), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)

        if self.hasFocus() and self.isEnabled():
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(235, 242, 247, 92), 1.0, Qt.PenStyle.DotLine))
            p.drawRoundedRect(rect.adjusted(3.0, 3.0, -3.0, -3.0), 10.0, 10.0)


class SettingCard(QFrame):
    def __init__(self, icon_name: str, title: str, description: str, *, value: int | None = None, enabled: bool = True, parent=None):
        super().__init__(parent)
        self.setObjectName("SettingCard")
        self.setMinimumWidth(160)
        self.setFixedHeight(150)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._hover_progress = 0.0
        self._hover_anim = QPropertyAnimation(self, b"hoverProgress", self)
        self._hover_anim.setDuration(170)
        self._hover_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(6)
        top = QHBoxLayout(); top.setSpacing(8)
        icon = QLabel(); icon.setObjectName("CardIcon")
        icon.setPixmap(make_icon(icon_name, "#bbc6d0", 72).pixmap(24, 24))
        icon.setFixedSize(28, 28)
        top.addWidget(icon); top.addStretch(1)
        self.toggle = ToggleSwitch(enabled); top.addWidget(self.toggle)
        outer.addLayout(top)

        title_label = QLabel(title); title_label.setObjectName("CardTitle")
        desc = QLabel(description); desc.setObjectName("CardDescription"); desc.setWordWrap(True)
        desc.setMaximumHeight(34)
        outer.addWidget(title_label); outer.addWidget(desc); outer.addStretch(1)

        self.bottom = QHBoxLayout(); self.bottom.setSpacing(7)
        self.slider: QSlider | None = None
        self.value_label: QLabel | None = None
        if value is not None:
            self.slider = GlassSlider(Qt.Orientation.Horizontal, track_height=4, handle_diameter=13); self.slider.setRange(0, 100); self.slider.setValue(value)
            self.value_label = QLabel(f"{value}%"); self.value_label.setObjectName("ValueLabel"); self.value_label.setMinimumWidth(34)
            self.value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.slider.valueChanged.connect(lambda v: self.value_label.setText(f"{v}%"))
            self.bottom.addWidget(self.slider, 1); self.bottom.addWidget(self.value_label)
        outer.addLayout(self.bottom)

    def _get_hover_progress(self) -> float:
        return self._hover_progress

    def _set_hover_progress(self, value: float) -> None:
        self._hover_progress = max(0.0, min(1.0, float(value)))
        self.update()

    hoverProgress = Property(float, _get_hover_progress, _set_hover_progress)

    def _animate_hover(self, target: float) -> None:
        if not ui_animations_enabled():
            self._set_hover_progress(target)
            return
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_progress)
        self._hover_anim.setEndValue(target)
        self._hover_anim.start()

    def enterEvent(self, event):
        self._animate_hover(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._animate_hover(0.0)
        super().leaveEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._hover_progress <= 0.001:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
        p.setPen(QPen(QColor(226, 235, 242, int(46 * self._hover_progress)), 1.0))
        p.setBrush(QColor(255, 255, 255, int(8 * self._hover_progress)))
        p.drawRoundedRect(rect, 12.0, 12.0)

    def value(self) -> int:
        return self.slider.value() if self.slider is not None else 0

    def set_value(self, value: int) -> None:
        if self.slider is not None:
            self.slider.setValue(value)


class SettingsDialog(QDialog):
    """Glass settings sheet with live component installation controls."""

    INSTALLS = {
        # DeepFilterNet's own README instructs installing PyTorch/torchaudio
        # before the wheel, so keep that as a two-step operation.
        "DeepFilterNet": [
            ["-m", "pip", "install", "--disable-pip-version-check", "--no-input", "--upgrade", "torch", "torchaudio"],
            ["-m", "pip", "install", "--disable-pip-version-check", "--no-input", "--upgrade", "deepfilternet"],
        ],
        "Silero VAD": [
            ["-m", "pip", "install", "--disable-pip-version-check", "--no-input", "--upgrade", "silero-vad"],
        ],
    }

    def __init__(self, parent: "MainWindow"):
        super().__init__(parent)
        self.owner = parent
        self.setWindowTitle("Настройки")
        self.setModal(True)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(650, 465)
        self._process: QProcess | None = None
        self._install_component: str | None = None
        self._install_steps: list[list[str]] = []
        self._component_widgets: dict[str, tuple[QLabel, QPushButton | None]] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        panel = QFrame(); panel.setObjectName("SettingsPanel")
        root.addWidget(panel)
        layout = QVBoxLayout(panel); layout.setContentsMargins(20, 15, 20, 16); layout.setSpacing(11)

        header = QHBoxLayout(); header.setSpacing(9)
        icon = QLabel(); icon.setPixmap(make_icon("settings", "#e5ebf0", 96).pixmap(24, 24)); icon.setFixedSize(28, 28)
        header.addWidget(icon)
        title_box = QVBoxLayout(); title_box.setSpacing(0)
        title = QLabel("Настройки"); title.setObjectName("SettingsTitle")
        sub = QLabel("Интерфейс и системные компоненты"); sub.setObjectName("SettingsMuted")
        title_box.addWidget(title); title_box.addWidget(sub); header.addLayout(title_box); header.addStretch(1)
        close_btn = CaptionButton("close", self); close_btn.clicked.connect(self.accept); header.addWidget(close_btn)
        layout.addLayout(header)

        ui_card = QFrame(); ui_card.setObjectName("SettingsCard")
        ui_layout = QHBoxLayout(ui_card); ui_layout.setContentsMargins(14, 11, 14, 11); ui_layout.setSpacing(12)
        ui_icon = QLabel(); ui_icon.setPixmap(make_icon("sparkles", "#cbd5dd", 96).pixmap(22, 22)); ui_icon.setFixedSize(26, 26); ui_layout.addWidget(ui_icon)
        ui_text = QVBoxLayout(); ui_text.setSpacing(1)
        ui_name = QLabel("Плавные анимации интерфейса"); ui_name.setObjectName("SettingsRowTitle")
        ui_desc = QLabel("Наведение на карточки и плавное переключение тумблеров"); ui_desc.setObjectName("SettingsMuted")
        ui_text.addWidget(ui_name); ui_text.addWidget(ui_desc); ui_layout.addLayout(ui_text, 1)
        self.animation_toggle = ToggleSwitch(ui_animations_enabled()); ui_layout.addWidget(self.animation_toggle)
        self.animation_toggle.toggled.connect(lambda checked: QSettings("ReelAudioStudio", "ReelAudioStudio").setValue("ui_animations", checked))
        layout.addWidget(ui_card)

        section = QLabel("СИСТЕМНЫЕ КОМПОНЕНТЫ"); section.setObjectName("SettingsSection"); layout.addWidget(section)
        self.components_layout = QVBoxLayout(); self.components_layout.setSpacing(7); layout.addLayout(self.components_layout)
        self._build_component_rows()

        self.install_feedback = QLabel("")
        self.install_feedback.setObjectName("InstallFeedback")
        self.install_feedback.setWordWrap(True)
        self.install_feedback.setVisible(False)
        layout.addWidget(self.install_feedback)

        self.install_progress = QProgressBar()
        self.install_progress.setRange(0, 0)
        self.install_progress.setTextVisible(False)
        self.install_progress.setFixedHeight(4)
        self.install_progress.setVisible(False)
        layout.addWidget(self.install_progress)

        local = QLabel("Все медиафайлы обрабатываются локально на этом ПК. Для установки AI-модулей интернет нужен только во время загрузки пакетов.")
        local.setObjectName("SettingsMuted"); local.setWordWrap(True); layout.addWidget(local)
        layout.addStretch(1)

        buttons = QHBoxLayout(); buttons.addStretch(1)
        done = QPushButton("Готово"); done.setObjectName("SettingsDone"); done.setFixedWidth(112); done.clicked.connect(self.accept); buttons.addWidget(done)
        layout.addLayout(buttons)

        self.setStyleSheet(r"""
            QDialog { background: transparent; }
            QFrame#SettingsPanel { background: rgba(31,39,47,248); border:1px solid rgba(218,228,236,68); border-radius:16px; }
            QLabel#SettingsTitle { color:#f2f5f7; font-size:17px; font-weight:750; }
            QLabel#SettingsMuted { color:#919da8; font-size:10px; }
            QLabel#SettingsSection { color:#aeb9c3; font-size:9px; font-weight:750; letter-spacing:1px; padding-top:3px; }
            QFrame#SettingsCard, QFrame#SettingsRow { background:rgba(74,86,97,70); border:1px solid rgba(217,226,234,36); border-radius:9px; }
            QFrame#SettingsRow:hover { background:rgba(88,101,113,78); border-color:rgba(221,230,238,54); }
            QLabel#SettingsRowTitle { color:#e9eef2; font-size:11px; font-weight:650; }
            QLabel#SettingsDotOk, QLabel#SettingsStateOk { color:#c8d5dd; font-size:10px; font-weight:650; }
            QLabel#SettingsDotOff, QLabel#SettingsStateOff { color:#818c96; font-size:10px; }
            QLabel#InstallFeedback { color:#aebbc5; font-size:10px; padding:2px 4px; }
            QLabel#InstallFeedback[error="true"] { color:#e2a1a1; }
            QPushButton#InstallButton { min-width:88px; background:rgba(108,122,134,110); border:1px solid rgba(221,230,237,58); border-radius:7px; padding:5px 9px; color:#eef2f5; font-size:10px; font-weight:700; }
            QPushButton#InstallButton:hover { background:rgba(133,148,160,145); border-color:rgba(235,241,246,88); }
            QPushButton#InstallButton:pressed { background:rgba(80,92,102,155); }
            QPushButton#InstallButton:disabled { color:#76818a; background:rgba(55,63,71,72); border-color:rgba(180,190,199,26); }
            QPushButton#SettingsDone { background:rgba(235,240,244,238); color:#232c33; border:1px solid rgba(255,255,255,245); border-radius:8px; padding:7px 12px; font-weight:750; }
            QPushButton#SettingsDone:hover { background:#ffffff; }
            QProgressBar { background:rgba(91,102,112,58); border:none; border-radius:2px; }
            QProgressBar::chunk { background:rgba(211,222,230,180); border-radius:2px; }
            QToolTip { background:#313b44; color:#ecf1f5; border:1px solid #596671; padding:5px; }
        """)

    def _component_info(self) -> list[tuple[str, bool, str, str]]:
        ff = find_executable("ffmpeg")
        fp = find_executable("ffprobe")
        deep_ok = deepfilter_available()
        silero_ok = silero_available()
        return [
            ("FFmpeg", bool(ff), "Готов к обработке" if ff else "Не найден", ff or "Добавьте ffmpeg.exe в папку bin"),
            ("FFprobe", bool(fp), "Готов" if fp else "Не найден", fp or "Добавьте ffprobe.exe в папку bin"),
            ("DeepFilterNet", deep_ok, "Установлен" if deep_ok else "Не установлен", "AI-шумоподавление DeepFilterNet"),
            ("Silero VAD", silero_ok, "Установлен" if silero_ok else "Не установлен", "Определение речи и пауз Silero VAD"),
        ]

    def _build_component_rows(self) -> None:
        while self.components_layout.count():
            item = self.components_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._component_widgets.clear()

        for name, ok, state, tip in self._component_info():
            row = QFrame(); row.setObjectName("SettingsRow")
            row_l = QHBoxLayout(row); row_l.setContentsMargins(12, 7, 9, 7); row_l.setSpacing(9)
            dot = QLabel("●"); dot.setObjectName("SettingsDotOk" if ok else "SettingsDotOff"); dot.setFixedWidth(12); row_l.addWidget(dot)
            name_l = QLabel(name); name_l.setObjectName("SettingsRowTitle"); row_l.addWidget(name_l)
            row_l.addStretch(1)
            state_l = QLabel(state); state_l.setObjectName("SettingsStateOk" if ok else "SettingsStateOff"); state_l.setToolTip(str(tip)); row_l.addWidget(state_l)

            install_btn: QPushButton | None = None
            if name in self.INSTALLS:
                install_btn = QPushButton("Установлено" if ok else "Установить")
                install_btn.setObjectName("InstallButton")
                install_btn.setEnabled(not ok)
                install_btn.setCursor(Qt.CursorShape.PointingHandCursor if not ok else Qt.CursorShape.ArrowCursor)
                if not ok:
                    install_btn.clicked.connect(lambda checked=False, component=name: self._install(component))
                row_l.addWidget(install_btn)
            self._component_widgets[name] = (state_l, install_btn)
            self.components_layout.addWidget(row)

    def _python_for_install(self) -> str | None:
        # In the normal run_windows.bat workflow sys.executable is the .venv
        # Python, which is the correct interpreter to extend.  A frozen PyInstaller
        # executable cannot run "-m pip", so look for a side-by-side development
        # venv before falling back to Python from PATH.
        if not getattr(sys, "frozen", False):
            return sys.executable
        roots = [Path(sys.executable).resolve().parent, Path(sys.executable).resolve().parent.parent]
        for root in roots:
            candidate = root / ".venv" / "Scripts" / "python.exe"
            if candidate.exists():
                return str(candidate)
        return shutil.which("python")

    def _install(self, component: str) -> None:
        if self._process is not None:
            return
        python = self._python_for_install()
        if not python:
            self._set_feedback("Не найден Python для установки модулей. Запустите проект через run_windows.bat или установите AI перед сборкой EXE.", error=True)
            return

        self._install_component = component
        self._install_steps = [list(step) for step in self.INSTALLS[component]]
        self.install_progress.setVisible(True)
        self._set_feedback(f"Подготавливаю установку {component}… Это может занять несколько минут.")
        for _name, (_state, button) in self._component_widgets.items():
            if button is not None:
                button.setEnabled(False)
        self._install_python = python
        self._start_install_step()

    def _start_install_step(self) -> None:
        if not self._install_steps:
            importlib.invalidate_caches()
            self.install_progress.setVisible(False)
            component = self._install_component or "AI-компонент"
            self._set_feedback(f"{component} установлен. Статус обновлён.")
            self._install_component = None
            self._process = None
            self._build_component_rows()
            self.owner._refresh_ai_controls()
            return

        args = self._install_steps.pop(0)
        process = QProcess(self)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.readyReadStandardOutput.connect(self._read_install_output)
        process.finished.connect(self._install_finished)
        process.errorOccurred.connect(self._install_process_error)
        self._process = process
        process.start(self._install_python, args)

    def _read_install_output(self) -> None:
        if self._process is None:
            return
        text = bytes(self._process.readAllStandardOutput()).decode("utf-8", errors="replace").strip()
        if text:
            # Keep the sheet clean: show only the last meaningful pip line.
            line = next((x.strip() for x in reversed(text.splitlines()) if x.strip()), "")
            if line:
                self._set_feedback(line[:130])

    def _install_finished(self, exit_code: int, _exit_status) -> None:
        if exit_code != 0:
            self.install_progress.setVisible(False)
            component = self._install_component or "AI-компонент"
            self._set_feedback(f"Не удалось установить {component}. Проверьте интернет и совместимость версии Python.", error=True)
            self._process = None
            self._install_component = None
            self._build_component_rows()
            return
        self._process = None
        self._start_install_step()

    def _install_process_error(self, _error) -> None:
        if self._process is None:
            return
        self.install_progress.setVisible(False)
        self._set_feedback("Не удалось запустить установщик Python.", error=True)
        self._process = None
        self._install_component = None
        self._build_component_rows()

    def _set_feedback(self, text: str, *, error: bool = False) -> None:
        self.install_feedback.setText(text)
        self.install_feedback.setProperty("error", error)
        self.install_feedback.style().unpolish(self.install_feedback)
        self.install_feedback.style().polish(self.install_feedback)
        self.install_feedback.setVisible(bool(text))

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() <= 62:
            wh = self.windowHandle()
            if wh and wh.startSystemMove():
                event.accept(); return
        super().mousePressEvent(event)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Reel Audio Studio")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor(0, 0, 0, 0))
        self.setPalette(palette)
        self.setMinimumSize(1120, 800)
        self.resize(1400, 850)

        self.input_path: Path | None = None
        self.processed_path: Path | None = None
        self._temp_root = Path(tempfile.mkdtemp(prefix="reelaudio_preview_"))
        self.processing_thread: ProcessingThread | None = None
        self.wave_thread: WaveformThread | None = None
        self._seeking = False
        self._last_info: dict | None = None
        saved_recent = QSettings("ReelAudioStudio", "ReelAudioStudio").value("recent_files", [])
        if isinstance(saved_recent, str):
            saved_recent = [saved_recent] if saved_recent else []
        self._recent = list(saved_recent or [])

        self.audio_out = QAudioOutput(self); self.audio_out.setVolume(0.9)
        self.player = QMediaPlayer(self); self.player.setAudioOutput(self.audio_out)
        self.player.positionChanged.connect(self._on_position)
        self.player.durationChanged.connect(self._on_duration)
        self.player.playbackStateChanged.connect(self._on_playback_state)

        central = QWidget(); central.setObjectName("TransparentRoot")
        self.setCentralWidget(central)
        self.window_layout = QVBoxLayout(central); self.window_layout.setContentsMargins(0, 0, 0, 0); self.window_layout.setSpacing(0)

        self.shell = GlassShell()
        self.window_layout.addWidget(self.shell)

        shell_layout = QVBoxLayout(self.shell); shell_layout.setContentsMargins(0, 0, 0, 0); shell_layout.setSpacing(0)
        self.title_bar = TitleBar(self); shell_layout.addWidget(self.title_bar)

        body = QWidget(); body.setObjectName("Body")
        shell_layout.addWidget(body, 1)
        layout = QVBoxLayout(body); layout.setContentsMargins(18, 5, 18, 10); layout.setSpacing(9)

        # File picker / drop area
        self.drop = DropFrame(self.load_file)
        self.drop.setFixedHeight(70)
        drop_layout = QHBoxLayout(self.drop); drop_layout.setContentsMargins(14, 10, 14, 10); drop_layout.setSpacing(12)
        self.add_file_btn = FileAddButton(); self.add_file_btn.clicked.connect(self.open_file); drop_layout.addWidget(self.add_file_btn)
        file_box = QVBoxLayout(); file_box.setSpacing(2)
        self.file_label = QLabel("Выберите видео или перетащите файл сюда"); self.file_label.setObjectName("FileLabel")
        self.file_hint = QLabel("MP4, MOV, MKV, WebM, WAV, MP3  •  локальная обработка"); self.file_hint.setObjectName("Muted")
        file_box.addStretch(1); file_box.addWidget(self.file_label); file_box.addWidget(self.file_hint); file_box.addStretch(1)
        drop_layout.addLayout(file_box, 1)
        self.remove_file_btn = QPushButton("Убрать файл"); self.remove_file_btn.setObjectName("RemoveFileButton"); self.remove_file_btn.setIcon(make_icon("x", "#cbd4dc")); self.remove_file_btn.setIconSize(QSize(17,17)); self.remove_file_btn.setToolTip("Убрать файл из проекта — файл на диске не удаляется"); self.remove_file_btn.clicked.connect(self.clear_selected_file); self.remove_file_btn.setVisible(False); drop_layout.addWidget(self.remove_file_btn)
        self.open_btn = QPushButton("Открыть файл"); self.open_btn.setObjectName("SecondaryButton"); self.open_btn.setIcon(make_icon("folder", "#dbe2e8")); self.open_btn.setIconSize(QSize(20,20)); self.open_btn.clicked.connect(self.open_file); drop_layout.addWidget(self.open_btn)
        self.history_btn = QPushButton("История"); self.history_btn.setObjectName("SecondaryButton"); self.history_btn.setIcon(make_icon("history", "#dbe2e8")); self.history_btn.setIconSize(QSize(20,20)); self.history_btn.clicked.connect(self.show_history_menu); drop_layout.addWidget(self.history_btn)
        layout.addWidget(self.drop)

        # Presets
        preset_row = QHBoxLayout(); preset_row.setSpacing(7)
        self.preset_group = QButtonGroup(self); self.preset_group.setExclusive(True); self.preset_buttons: dict[str, QPushButton] = {}
        preset_defs = [
            ("Auto", "sparkles", "AUTO", "Автоматическая обработка"),
            ("Voice Clean", "mic", "VOICE CLEAN", "Чистый голос"),
            ("Street / Car", "car", "STREET", "Улица / Машина"),
            ("Voice + Music", "music", "VOICE + MUSIC", "Голос + Музыка"),
            ("Podcast", "users", "PODCAST", "Интервью / Подкаст"),
        ]
        for key, icon_name, title, desc in preset_defs:
            btn = AnimatedPresetButton(f"{title}\n{desc}"); btn.setCheckable(True); btn.setObjectName("PresetButton"); btn.setFixedHeight(62)
            btn.setIcon(make_state_icon(icon_name, "#c5ced6", "#273038")); btn.setIconSize(QSize(23,23))
            btn.clicked.connect(lambda checked, name=key: self.apply_preset(name) if checked else None)
            self.preset_group.addButton(btn); self.preset_buttons[key] = btn; preset_row.addWidget(btn, 1)
        self.preset_buttons["Auto"].setChecked(True); layout.addLayout(preset_row)

        # Waveform / player
        self.media_panel = QFrame(); self.media_panel.setObjectName("Panel"); self.media_panel.setFixedHeight(244)
        media_layout = QVBoxLayout(self.media_panel); media_layout.setContentsMargins(15, 12, 15, 11); media_layout.setSpacing(7)
        media_header = QHBoxLayout(); media_header.setSpacing(7)
        media_names = QVBoxLayout(); media_names.setSpacing(1)
        self.media_name = QLabel("Файл не выбран"); self.media_name.setObjectName("MediaName")
        self.media_meta = QLabel("Перетащите ролик в область выше"); self.media_meta.setObjectName("Muted")
        media_names.addWidget(self.media_name); media_names.addWidget(self.media_meta); media_header.addLayout(media_names,1)
        self.before_btn = QPushButton("До обработки"); self.before_btn.setObjectName("CompareButton"); self.before_btn.setCheckable(True); self.before_btn.setChecked(True); self.before_btn.clicked.connect(lambda: self.switch_source(False)); media_header.addWidget(self.before_btn)
        self.after_btn = QPushButton("После обработки"); self.after_btn.setObjectName("CompareButton"); self.after_btn.setCheckable(True); self.after_btn.setEnabled(False); self.after_btn.clicked.connect(lambda: self.switch_source(True)); media_header.addWidget(self.after_btn)
        self.time_label = QLabel("00:00 / 00:00"); self.time_label.setObjectName("TimeLabel"); media_header.addWidget(self.time_label)
        # v10: removed the duplicate expand/maximize button from the media header.
        # Window maximize/restore remains available from the native title bar.
        media_layout.addLayout(media_header)

        self.waveform = WaveformWidget(); self.waveform.setMinimumHeight(118); self.waveform.setMaximumHeight(136); media_layout.addWidget(self.waveform, 1)
        self.timeline = GlassSlider(Qt.Orientation.Horizontal, track_height=3, handle_diameter=11); self.timeline.setObjectName("Timeline"); self.timeline.setRange(0,0); self.timeline.setFixedHeight(18)
        self.timeline.sliderPressed.connect(lambda: setattr(self, "_seeking", True)); self.timeline.sliderReleased.connect(self._seek_release); media_layout.addWidget(self.timeline)
        transport = QHBoxLayout(); transport.setSpacing(9)
        self.play_btn = QPushButton(); self.play_btn.setObjectName("PlayButton"); self.play_btn.setIcon(make_icon("play", "#f1f5f8")); self.play_btn.setIconSize(QSize(22,22)); self.play_btn.setFixedSize(46,46); self.play_btn.clicked.connect(self.toggle_play); self.play_btn.setEnabled(False); transport.addWidget(self.play_btn)
        self.skip_back = QPushButton(); self.skip_back.setObjectName("TransportButton"); self.skip_back.setIcon(make_icon("skip-back", "#cbd4dc")); self.skip_back.setIconSize(QSize(19,19)); self.skip_back.clicked.connect(lambda: self.player.setPosition(max(0, self.player.position()-5000))); transport.addWidget(self.skip_back)
        self.skip_forward = QPushButton(); self.skip_forward.setObjectName("TransportButton"); self.skip_forward.setIcon(make_icon("skip-forward", "#cbd4dc")); self.skip_forward.setIconSize(QSize(19,19)); self.skip_forward.clicked.connect(lambda: self.player.setPosition(min(self.player.duration(), self.player.position()+5000))); transport.addWidget(self.skip_forward)
        vol_icon = QLabel(); vol_icon.setPixmap(make_icon("volume", "#bdc7d0").pixmap(21,21)); vol_icon.setFixedSize(24,24); transport.addWidget(vol_icon)
        self.volume_slider = GlassSlider(Qt.Orientation.Horizontal, track_height=4, handle_diameter=13); self.volume_slider.setRange(0,100); self.volume_slider.setValue(90); self.volume_slider.setFixedWidth(210); self.volume_slider.valueChanged.connect(lambda v: self.audio_out.setVolume(v/100.0)); transport.addWidget(self.volume_slider)
        transport.addStretch(1)
        self.rate = GlassComboBox(); self.rate.setObjectName("CompactCombo"); self.rate.addItems(["0.75x","1.0x","1.25x","1.5x"]); self.rate.setCurrentText("1.0x"); self.rate.currentTextChanged.connect(lambda t: self.player.setPlaybackRate(float(t[:-1]))); transport.addWidget(self.rate)
        media_layout.addLayout(transport); layout.addWidget(self.media_panel)

        # Setting cards; responsive 6x1 on wide windows, 3x2 on narrower windows.
        self.cards_widget = QWidget(); self.cards_grid = QGridLayout(self.cards_widget); self.cards_grid.setContentsMargins(0,0,0,0); self.cards_grid.setHorizontalSpacing(8); self.cards_grid.setVerticalSpacing(8)
        self.noise_card = SettingCard("waves", "Шумоподавление", "Убирает фоновые шумы, ветер и гул", value=70)
        self.presence_card = SettingCard("voice", "Выразительность голоса", "Делает голос яснее и ближе", value=60)
        self.compression_card = SettingCard("compression", "Компрессия", "Выравнивает громкость и удерживает пики", value=50)
        self.ducking_card = SettingCard("music", "Приглушение музыки", "Автоматически снижает музыку во время речи", value=70, enabled=False)
        self.ducking_card.toggle.setEnabled(False)
        if self.ducking_card.slider: self.ducking_card.slider.setEnabled(False)
        self.ducking_card.setToolTip("Модуль разделения голоса и музыки пока не подключён.")
        self.pause_card = SettingCard("scissors", "Удаление длинных пауз", "Находит тишину и синхронно сокращает видео", value=None, enabled=False)
        self.keep_pause = GlassComboBox(); self.keep_pause.setObjectName("CardCombo"); self.keep_pause.addItems(["120 мс","180 мс","250 мс","350 мс"]); self.keep_pause.setCurrentText("180 мс"); self.pause_card.bottom.addWidget(self.keep_pause,1)
        self.ai_vad = QPushButton("Silero"); self.ai_vad.setObjectName("ChipButton"); self.ai_vad.setCheckable(True); self.ai_vad.setEnabled(silero_available()); self.ai_vad.setIcon(make_state_icon("sparkles", "#bfc9d1", "#29323a")); self.ai_vad.setIconSize(QSize(14,14)); self.pause_card.bottom.addWidget(self.ai_vad)
        if not silero_available(): self.ai_vad.setToolTip("Опционально: pip install silero-vad")
        self.normalize_card = SettingCard("normalize", "Авто-нормализация", "Приводит громкость к выбранной цели LUFS", value=None, enabled=True)
        self.lufs = GlassComboBox(); self.lufs.setObjectName("CardCombo"); self.lufs.addItems(["-16 LUFS","-14 LUFS","-12 LUFS"]); self.lufs.setCurrentText("-14 LUFS"); self.normalize_card.bottom.addWidget(self.lufs,1)
        self.deepfilter = QPushButton("DeepFilter"); self.deepfilter.setObjectName("ChipButton"); self.deepfilter.setCheckable(True); self.deepfilter.setEnabled(deepfilter_available()); self.deepfilter.setIcon(make_state_icon("sparkles", "#bfc9d1", "#29323a")); self.deepfilter.setIconSize(QSize(14,14)); self.noise_card.bottom.addWidget(self.deepfilter)
        if not deepfilter_available(): self.deepfilter.setToolTip("Опционально: pip install deepfilternet")
        self.card_list = [self.noise_card,self.presence_card,self.compression_card,self.ducking_card,self.pause_card,self.normalize_card]
        layout.addWidget(self.cards_widget)

        # Main action
        action_panel = QFrame(); action_panel.setObjectName("ActionPanel"); action_panel.setFixedHeight(60)
        action_layout = QHBoxLayout(action_panel); action_layout.setContentsMargins(10,7,10,7); action_layout.setSpacing(10)
        action_layout.addStretch(1)
        self.enhance_btn = AnimatedPrimaryButton("АВТОМАТИЧЕСКИ УЛУЧШИТЬ ЗВУК"); self.enhance_btn.setObjectName("Primary"); self.enhance_btn.clicked.connect(self.enhance); action_layout.addWidget(self.enhance_btn, 3)
        action_layout.addStretch(1)
        reset_btn = QPushButton("Сбросить всё"); reset_btn.setObjectName("GhostButton"); reset_btn.setIcon(make_icon("reset", "#bdc6cf")); reset_btn.setIconSize(QSize(17,17)); reset_btn.clicked.connect(lambda: self.apply_preset("Auto")); action_layout.addWidget(reset_btn)
        layout.addWidget(action_panel)

        # Export bar
        export_panel = QFrame(); export_panel.setObjectName("ExportPanel"); export_panel.setFixedHeight(70)
        export_layout = QHBoxLayout(export_panel); export_layout.setContentsMargins(14,9,14,9); export_layout.setSpacing(12)
        export_icon = QLabel(); export_icon.setPixmap(make_icon("upload", "#eef3f6", 128).pixmap(44,44)); export_icon.setFixedSize(50,50); export_icon.setAlignment(Qt.AlignmentFlag.AlignCenter); export_layout.addWidget(export_icon)
        export_text = QVBoxLayout(); export_text.setSpacing(1); et = QLabel("ЭКСПОРТИРОВАТЬ REEL"); et.setObjectName("ExportTitle"); es = QLabel("Сохранить обработанное видео на ПК"); es.setObjectName("Muted"); export_text.addWidget(et); export_text.addWidget(es); export_layout.addLayout(export_text,1)
        self.format_combo = GlassComboBox(lock_single=True); self.format_combo.addItems(["MP4 (H.264)"]); export_layout.addWidget(self.format_combo)
        self.quality_combo = GlassComboBox(lock_single=True); self.quality_combo.addItems(["Исходное качество"]); export_layout.addWidget(self.quality_combo)
        self.export_btn = QPushButton("Экспорт"); self.export_btn.setObjectName("ExportButton"); self.export_btn.setIcon(make_icon("upload", "#1e252b")); self.export_btn.setIconSize(QSize(21,21)); self.export_btn.setEnabled(False); self.export_btn.clicked.connect(self.export_result); export_layout.addWidget(self.export_btn)
        layout.addWidget(export_panel)

        # Footer / progress
        footer = QHBoxLayout(); footer.setSpacing(7)
        creator = QLabel("csezet"); creator.setObjectName("CreatorTag"); footer.addWidget(creator)
        creator_sep = QLabel("•"); creator_sep.setObjectName("FooterText"); footer.addWidget(creator_sep)
        self.status = QLabel("Готов к работе"); self.status.setObjectName("FooterText"); footer.addWidget(self.status)
        self.progress = QProgressBar(); self.progress.setRange(0,0); self.progress.setFixedWidth(145); self.progress.setFixedHeight(5); self.progress.setTextVisible(False); self.progress.setVisible(False); footer.addWidget(self.progress)
        footer.addStretch(1)
        layout.addLayout(footer)

        self.setStyleSheet(self._style())
        self._refresh_system_status(); self.apply_preset("Auto")
        self._create_resize_handles()
        # Realize the HWND while the window is still hidden, then restore the Win32
        # caption/resizable style bits. DWM sees a normal app window from its first
        # visible frame, so opening/minimize/restore use the native shell animation.
        self._native_animation_ready = enable_native_window_animations(int(self.winId()))
        QTimer.singleShot(0, self._finish_window_setup)

    # ---- native window chrome / layout -------------------------------------------------
    def _finish_window_setup(self):
        self._system_backdrop_active = apply_windows_backdrop(int(self.winId()), acrylic=True, material=False)
        self._reflow_cards()
        self._sync_window_state()

    def _create_resize_handles(self):
        L, R, T, B = Qt.Edge.LeftEdge, Qt.Edge.RightEdge, Qt.Edge.TopEdge, Qt.Edge.BottomEdge
        self._resize_handles = [
            ResizeHandle(self,L,Qt.CursorShape.SizeHorCursor), ResizeHandle(self,R,Qt.CursorShape.SizeHorCursor),
            ResizeHandle(self,T,Qt.CursorShape.SizeVerCursor), ResizeHandle(self,B,Qt.CursorShape.SizeVerCursor),
            ResizeHandle(self,L|T,Qt.CursorShape.SizeFDiagCursor), ResizeHandle(self,R|T,Qt.CursorShape.SizeBDiagCursor),
            ResizeHandle(self,L|B,Qt.CursorShape.SizeBDiagCursor), ResizeHandle(self,R|B,Qt.CursorShape.SizeFDiagCursor),
        ]

    def _position_resize_handles(self):
        if not hasattr(self, "_resize_handles"): return
        w,h,t = self.width(), self.height(), 6
        geometries = [(0,t,t,h-2*t),(w-t,t,t,h-2*t),(t,0,w-2*t,t),(t,h-t,w-2*t,t),(0,0,t,t),(w-t,0,t,t),(0,h-t,t,t),(w-t,h-t,t,t)]
        for handle, geo in zip(self._resize_handles, geometries):
            handle.setGeometry(*geo); handle.setVisible(not self.isMaximized()); handle.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event); self._position_resize_handles(); self._reflow_cards()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            QTimer.singleShot(0, self._sync_window_state)

    def _sync_window_state(self):
        maximized = self.isMaximized()
        # Borderless glass: the shell always reaches the native window edge.
        # Resize handles are transparent overlays, so no visible outer gutter is needed.
        self.window_layout.setContentsMargins(0, 0, 0, 0)
        self.shell.setProperty("maximized", maximized)
        self.shell.update()
        self.title_bar.max_btn.update(); self._position_resize_handles()

    def minimize_window(self):
        """Minimize through the Windows shell so DWM owns the taskbar transition."""
        if not show_window_native(int(self.winId()), SW_MINIMIZE):
            self.showMinimized()

    def toggle_maximize(self):
        command = SW_RESTORE if self.isMaximized() else SW_MAXIMIZE
        if not show_window_native(int(self.winId()), command):
            self.showNormal() if self.isMaximized() else self.showMaximized()
        QTimer.singleShot(0, self._sync_window_state)

    def nativeEvent(self, eventType, message):
        # Windows must retain WS_CAPTION/WS_THICKFRAME for native taskbar/DWM
        # animations, Snap and shell semantics. Returning 0 for WM_NCCALCSIZE
        # expands our Qt client area over that native frame, so it stays invisible.
        if is_nccalcsize_message(eventType, message):
            return True, 0
        return super().nativeEvent(eventType, message)

    def _reflow_cards(self):
        if not hasattr(self, "card_list"): return
        width = self.cards_widget.width() or self.width()
        cols = 6 if width >= 960 else 3
        for card in self.card_list: self.cards_grid.removeWidget(card)
        for i, card in enumerate(self.card_list): self.cards_grid.addWidget(card, i // cols, i % cols)
        self.cards_widget.setFixedHeight(150 if cols == 6 else 308)

    # ---- history / system --------------------------------------------------------------
    def _save_recent(self, path: Path):
        value = str(path.resolve())
        self._recent = [value] + [x for x in self._recent if x != value and Path(x).exists()]
        self._recent = self._recent[:8]
        QSettings("ReelAudioStudio", "ReelAudioStudio").setValue("recent_files", self._recent)

    def show_history_menu(self):
        menu = QMenu(self); menu.setObjectName("GlassMenu")
        valid = [p for p in self._recent if Path(p).exists()]
        if not valid:
            action = menu.addAction("История пока пуста"); action.setEnabled(False)
        else:
            for p in valid:
                action = menu.addAction(make_icon("folder", "#c8d1d9"), Path(p).name)
                action.setToolTip(p); action.triggered.connect(lambda checked=False, path=p: self.load_file(path))
            menu.addSeparator(); clear = menu.addAction("Очистить историю"); clear.triggered.connect(self.clear_history)
        menu.exec(self.history_btn.mapToGlobal(self.history_btn.rect().bottomLeft()))

    def clear_history(self):
        self._recent = []; QSettings("ReelAudioStudio", "ReelAudioStudio").setValue("recent_files", [])

    def _refresh_system_status(self):
        self._ffmpeg_ready = bool(find_executable("ffmpeg")) and bool(find_executable("ffprobe"))
        if hasattr(self, "enhance_btn"):
            running = bool(self.processing_thread and self.processing_thread.isRunning())
            # Keep the primary action hoverable before media is selected.  A click
            # without media gives feedback instead of being a dead disabled control.
            self.enhance_btn.setEnabled(self._ffmpeg_ready and not running)

    def _refresh_ai_controls(self):
        deep_ok = deepfilter_available()
        silero_ok = silero_available()
        self.deepfilter.setEnabled(deep_ok)
        self.ai_vad.setEnabled(silero_ok)
        self.deepfilter.setToolTip("" if deep_ok else "Установите DeepFilterNet через Настройки")
        self.ai_vad.setToolTip("" if silero_ok else "Установите Silero VAD через Настройки")

    def show_settings(self):
        dialog = SettingsDialog(self)
        dialog.exec()

    # ---- media ------------------------------------------------------------------------
    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(self,"Открыть Reel","","Media (*.mp4 *.mov *.mkv *.avi *.webm *.wav *.mp3 *.m4a *.flac *.aac);;Все файлы (*.*)")
        if path: self.load_file(path)

    def load_file(self, path: str):
        p = Path(path)
        if not p.exists() or p.suffix.lower() not in SUPPORTED:
            QMessageBox.warning(self,"Файл не поддерживается","Выберите видео или аудиофайл поддерживаемого формата."); return
        try: info = media_summary(p)
        except Exception as exc: QMessageBox.critical(self,"Не удалось открыть файл",str(exc)); return
        if not info["has_audio"]:
            QMessageBox.warning(self,"Нет звука","В файле не найден аудиопоток."); return
        self._last_info = info; self.player.stop(); self.input_path = p; self.processed_path = None; self._save_recent(p)
        self.file_label.setText(p.name); self.file_hint.setText("Файл загружен  •  настройте обработку или выберите пресет")
        self.media_name.setText(p.name)
        meta = [self._fmt_ms(int(info["duration"]*1000))]; video=info.get("video") or {}; audio=info.get("audio") or {}
        if video.get("width") and video.get("height"): meta.append(f"{video['width']}×{video['height']}")
        if audio.get("codec_name"): meta.append(str(audio["codec_name"]).upper())
        if audio.get("sample_rate"):
            try: meta.append(f"{int(audio['sample_rate'])//1000} kHz")
            except (TypeError,ValueError): pass
        self.media_meta.setText("  •  ".join(meta)); self.player.setSource(QUrl.fromLocalFile(str(p.resolve())))
        self.waveform.set_duration(int(info["duration"]*1000)); self.play_btn.setEnabled(True)
        self.remove_file_btn.setVisible(True); self.remove_file_btn.setEnabled(True)
        self.enhance_btn.setEnabled(self._ffmpeg_ready)
        self.after_btn.setEnabled(False); self.export_btn.setEnabled(False); self.before_btn.setChecked(True); self.after_btn.setChecked(False)
        self.status.setText("Строю waveform…"); self._load_waveform(str(p))

    def clear_selected_file(self):
        """Detach the current media from the project without deleting it on disk."""
        if self.processing_thread and self.processing_thread.isRunning():
            self.status.setText("Дождитесь окончания обработки перед сменой файла")
            return

        if self.wave_thread and self.wave_thread.isRunning():
            self.wave_thread.requestInterruption()

        self.player.stop()
        # Qt documents that a null QUrl discards all data for the current source
        # and stops related I/O, which is exactly what a project-level clear needs.
        self.player.setSource(QUrl())

        old_preview = self.processed_path
        self.input_path = None
        self.processed_path = None
        self._last_info = None

        if old_preview:
            try:
                old_preview.resolve().relative_to(self._temp_root.resolve())
                old_preview.unlink(missing_ok=True)
            except (ValueError, OSError):
                pass

        self.file_label.setText("Выберите видео или перетащите файл сюда")
        self.file_hint.setText("MP4, MOV, MKV, WebM, WAV, MP3  •  локальная обработка")
        self.media_name.setText("Файл не выбран")
        self.media_meta.setText("Перетащите ролик в область выше")
        self.time_label.setText("00:00 / 00:00")
        self.timeline.setRange(0, 0)
        self.timeline.setValue(0)
        self.waveform.set_peaks([])
        self.waveform.set_duration(0)
        self.waveform.set_progress(0.0)
        self.play_btn.setEnabled(False)
        self.after_btn.setEnabled(False)
        self.export_btn.setEnabled(False)
        self.before_btn.setChecked(True)
        self.after_btn.setChecked(False)
        self.remove_file_btn.setVisible(False)
        self.enhance_btn.setEnabled(self._ffmpeg_ready)
        self.status.setText("Файл убран  •  выберите новый ролик или аудио")

    def _load_waveform(self, path: str):
        if self.wave_thread and self.wave_thread.isRunning(): self.wave_thread.requestInterruption()
        self.wave_thread = WaveformThread(path,self); self.wave_thread.done.connect(self._wave_ready); self.wave_thread.failed.connect(lambda e: self.status.setText(f"Waveform: {e}")); self.wave_thread.start()

    def _wave_ready(self, peaks: list):
        self.waveform.set_peaks(peaks); self.status.setText("Готов к обработке")

    # ---- presets / processing ----------------------------------------------------------
    def apply_preset(self, name: str):
        presets = {"Auto":(70,60,50,True,True,-14),"Voice Clean":(58,55,48,False,True,-14),"Street / Car":(82,62,58,True,True,-14),"Natural":(28,30,32,False,True,-16),"Voice + Music":(38,42,40,False,True,-14),"Podcast":(48,52,46,True,True,-16)}
        n,p,c,pauses,normalize,lufs = presets.get(name,presets["Auto"])
        self.noise_card.set_value(n); self.presence_card.set_value(p); self.compression_card.set_value(c)
        self.noise_card.toggle.setChecked(n>0); self.presence_card.toggle.setChecked(p>0); self.compression_card.toggle.setChecked(c>0)
        self.pause_card.toggle.setChecked(pauses); self.normalize_card.toggle.setChecked(normalize); self.lufs.setCurrentText(f"{lufs} LUFS")
        if name in self.preset_buttons: self.preset_buttons[name].setChecked(True)

    def _settings(self) -> ProcessingSettings:
        keep_ms = int(self.keep_pause.currentText().split()[0])
        return ProcessingSettings(
            preset=next((k for k,b in self.preset_buttons.items() if b.isChecked()),"Auto"),
            noise_removal=self.noise_card.value() if self.noise_card.toggle.isChecked() else 0,
            voice_presence=self.presence_card.value() if self.presence_card.toggle.isChecked() else 0,
            compression=self.compression_card.value() if self.compression_card.toggle.isChecked() else 0,
            remove_pauses=self.pause_card.toggle.isChecked(), keep_pause_seconds=keep_ms/1000.0,
            target_lufs=float(self.lufs.currentText().split()[0]), auto_normalize=self.normalize_card.toggle.isChecked(),
            ai_deepfilter=self.deepfilter.isChecked(), ai_vad=self.ai_vad.isChecked(),
        )

    def enhance(self):
        if not self._ffmpeg_ready:
            self.enhance_btn.pulse_attention()
            self.status.setText("FFmpeg/FFprobe не найдены • откройте Настройки")
            return
        if not self.input_path:
            self.enhance_btn.pulse_attention()
            self.status.setText("Сначала выберите видео или аудио")
            return
        try: info = media_summary(self.input_path)
        except Exception as exc: QMessageBox.critical(self,"Ошибка",str(exc)); return
        suffix = ".mp4" if info["has_video"] else ".m4a"; preview = self._temp_root / f"preview_{uuid.uuid4().hex}{suffix}"
        self._set_busy(True); self.processing_thread = ProcessingThread(str(self.input_path),str(preview),self._settings(),self)
        self.processing_thread.stage.connect(self.status.setText); self.processing_thread.done.connect(self._process_done); self.processing_thread.failed.connect(self._process_failed); self.processing_thread.start()

    def _set_busy(self, busy: bool):
        self.progress.setVisible(busy)
        self.enhance_btn.setEnabled(not busy and self._ffmpeg_ready)
        self.remove_file_btn.setEnabled(not busy)
        self.export_btn.setEnabled(not busy and self.processed_path is not None)

    def _process_done(self, path: str):
        self.processed_path = Path(path); self.after_btn.setEnabled(True); self.export_btn.setEnabled(True); self._set_busy(False); self.status.setText("Готово  •  сравните До / После"); self.switch_source(True)

    def _process_failed(self, error: str):
        self._set_busy(False); self.status.setText("Ошибка обработки"); QMessageBox.critical(self,"Ошибка обработки",error)

    def switch_source(self, after: bool):
        source = self.processed_path if after else self.input_path
        if not source: return
        was_playing = self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        self.player.stop(); self.player.setSource(QUrl.fromLocalFile(str(source.resolve()))); self.before_btn.setChecked(not after); self.after_btn.setChecked(after)
        if was_playing: self.player.play()
        self._load_waveform(str(source))

    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState: self.player.pause()
        else: self.player.play()

    def _on_playback_state(self, state):
        name = "pause" if state == QMediaPlayer.PlaybackState.PlayingState else "play"
        self.play_btn.setIcon(make_icon(name,"#f1f5f8")); self.play_btn.setIconSize(QSize(22,22))

    def _on_duration(self, duration: int):
        self.timeline.setRange(0,max(0,duration)); self._update_time(self.player.position(),duration); self.waveform.set_duration(duration)

    def _on_position(self, pos: int):
        if not self._seeking: self.timeline.setValue(pos)
        duration=self.player.duration(); self._update_time(pos,duration); self.waveform.set_progress((pos/duration) if duration>0 else 0.0)

    def _seek_release(self):
        self._seeking=False; self.player.setPosition(self.timeline.value())

    def _update_time(self, pos: int, duration: int): self.time_label.setText(f"{self._fmt_ms(pos)} / {self._fmt_ms(duration)}")

    @staticmethod
    def _fmt_ms(ms: int) -> str:
        sec=max(0,ms//1000); return f"{sec//60:02d}:{sec%60:02d}"

    def export_result(self):
        if not self.processed_path: return
        default="enhanced_reel.mp4" if self.processed_path.suffix.lower()==".mp4" else "enhanced_audio.m4a"
        path,_=QFileDialog.getSaveFileName(self,"Экспорт",default,"MP4 (*.mp4);;M4A (*.m4a);;Все файлы (*.*)")
        if not path: return
        try: shutil.copy2(self.processed_path,path); self.status.setText(f"Экспортировано: {Path(path).name}")
        except Exception as exc: QMessageBox.critical(self,"Ошибка экспорта",str(exc))

    def closeEvent(self, event):
        self.player.stop(); shutil.rmtree(self._temp_root,ignore_errors=True); super().closeEvent(event)

    @staticmethod
    def _style() -> str:
        return r"""
        QWidget { background: transparent; color: #eaf0f5; font-family: 'Segoe UI'; font-size: 12px; }
        QWidget#TransparentRoot { background: transparent; }
        /* v6: no full-window plate.  The native window itself is truly transparent;
           only functional panels/cards below paint translucent surfaces. */
        /* The full-window glass plate is custom-painted by GlassShell.
           Keeping QSS transparent here prevents a second rectangular layer. */
        QFrame#GlassShell { background: transparent; border: none; }
        QFrame#GlassShell[maximized="true"] { background: transparent; border: none; }
        QWidget#TitleBar { background: transparent; border: none; }
        QLabel#Title { color:#f1f5f8; font-size:18px; font-weight:700; letter-spacing:2px; }
        QLabel#Subtitle { color:#8f9aa5; font-size:10px; font-weight:500; letter-spacing:1px; }
        QLabel#FileLabel, QLabel#MediaName { color:#eef3f7; font-size:13px; font-weight:650; }
        QLabel#Muted, QLabel#FooterText { color:#909ba6; font-size:11px; }
        QLabel#CreatorTag { color:#d5dde4; font-size:10px; font-weight:750; letter-spacing:1px; }
        QLabel#TimeLabel { color:#aeb8c2; padding-left:8px; }
        QLabel#CardTitle { color:#f0f4f7; font-size:12px; font-weight:700; }
        QLabel#CardDescription { color:#97a2ac; font-size:10px; }
        QLabel#ValueLabel { color:#dce3e8; font-weight:650; }
        QLabel#ExportTitle { color:#f2f5f7; font-size:14px; font-weight:750; letter-spacing:1px; }
        QLabel#SystemStatus[ok="true"] { color:#bac5ce; font-weight:650; }
        QLabel#SystemStatus[ok="false"] { color:#dc9696; font-weight:650; }

        QFrame#DropFrame, QFrame#Panel, QFrame#SettingCard, QFrame#ActionPanel, QFrame#ExportPanel {
            background: rgba(36,46,56,76); border:1px solid rgba(214,225,235,48); border-radius:12px;
        }
        QFrame#DropFrame:hover { background: rgba(55,68,80,94); border-color:rgba(220,230,238,76); }
        QFrame#Panel { background: rgba(18,26,34,72); }
        QFrame#SettingCard { background: rgba(49,60,70,82); }
        QFrame#ActionPanel { background: rgba(20,28,35,52); }
        QFrame#ExportPanel { background: rgba(103,116,128,78); }

        QPushButton { background:rgba(73,86,98,72); border:1px solid rgba(204,216,226,42); border-radius:8px; color:#e6ecf1; padding:7px 11px; font-weight:600; }
        QPushButton:hover { background:rgba(105,119,132,102); border-color:rgba(220,229,237,70); }
        QPushButton:pressed { background:rgba(52,63,73,118); }
        QPushButton:disabled { color:#69747e; background:rgba(44,51,58,82); border-color:rgba(150,160,170,22); }
        QPushButton#TitleGhostButton { background:transparent; border:1px solid transparent; color:#aeb8c1; padding:7px 10px; }
        QPushButton#TitleGhostButton:hover { background:rgba(255,255,255,12); border-color:rgba(255,255,255,18); }
        QPushButton#SecondaryButton { min-height:34px; min-width:118px; }
        QPushButton#RemoveFileButton { min-height:34px; min-width:92px; background:rgba(76,65,69,58); color:#cbd4dc; border-color:rgba(225,198,203,34); }
        QPushButton#RemoveFileButton:hover { background:rgba(126,66,73,95); color:#ffffff; border-color:rgba(238,167,176,78); }
        QPushButton#RemoveFileButton:pressed { background:rgba(99,51,58,118); }
        QPushButton#PresetButton { text-align:left; background:transparent; border:none; border-radius:9px; color:#b9c3cc; padding:8px 11px; font-size:10px; }
        QPushButton#PresetButton:checked { background:transparent; border:none; color:#273038; }
        QPushButton#CompareButton { min-width:118px; background:rgba(43,54,64,62); color:#99a4ae; padding:7px 12px; }
        QPushButton#CompareButton:checked { background:rgba(94,106,117,152); color:#f2f5f7; border-color:rgba(213,224,233,67); }
        QPushButton#SquareButton, QPushButton#TransportButton { min-width:0; padding:0; background:rgba(55,64,73,80); }
        QPushButton#TransportButton { border:none; width:34px; height:34px; }
        QPushButton#PlayButton { border-radius:23px; padding:0; background:rgba(121,133,144,128); border-color:rgba(225,233,239,52); }
        /* AnimatedPrimaryButton paints its own glass gradient, hover and attention pulse. */
        QPushButton#GhostButton { background:rgba(52,61,69,62); color:#acb6c0; }
        QPushButton#ExportButton { background:rgba(239,243,246,235); color:#20282f; border-color:rgba(255,255,255,238); font-weight:800; min-width:104px; }
        QPushButton#ExportButton:hover { background:#ffffff; }
        QPushButton#ChipButton { padding:4px 6px; border-radius:6px; font-size:9px; color:#aeb8c1; }
        QPushButton#ChipButton:checked { background:rgba(210,220,228,190); color:#29323a; }

        QComboBox { background:rgba(42,53,63,78); border:1px solid rgba(199,211,222,40); border-radius:7px; color:#dbe2e8; padding:6px 24px 6px 9px; min-width:108px; outline:0; }
        QComboBox:hover { background:rgba(54,66,77,88); border-color:rgba(218,227,235,68); }
        QComboBox:focus, QComboBox:on { background:rgba(54,66,77,88); border:1px solid rgba(218,227,235,68); outline:0; }
        QComboBox::drop-down { border:none; width:22px; background:transparent; }
        QComboBox::down-arrow { width:0px; height:0px; }
        QListView#GlassComboPopup { background:rgba(35,44,52,250); border:1px solid rgba(211,222,231,62); border-radius:8px; color:#edf2f5; padding:4px; outline:0; selection-background-color:rgba(94,108,120,190); selection-color:#ffffff; }
        QListView#GlassComboPopup::item { min-height:26px; padding:3px 8px; border-radius:5px; }
        QListView#GlassComboPopup::item:hover, QListView#GlassComboPopup::item:selected { background:rgba(94,108,120,190); }
        QComboBox#CompactCombo { min-width:76px; max-width:86px; }
        QComboBox#CardCombo { min-width:70px; padding:5px 7px; font-size:10px; }

        /* Sliders are custom-painted by GlassSlider to avoid native/QSS fill artifacts. */

        QProgressBar { background:rgba(96,106,115,55); border:none; border-radius:2px; }
        QProgressBar::chunk { background:rgba(210,220,228,170); border-radius:2px; }
        QMenu#GlassMenu { background:rgba(37,45,52,245); border:1px solid #53606b; border-radius:8px; padding:6px; }
        QMenu#GlassMenu::item { padding:7px 18px 7px 9px; border-radius:5px; }
        QMenu#GlassMenu::item:selected { background:rgba(96,111,124,130); }
        QToolTip { background:#313b44; color:#ecf1f5; border:1px solid #596671; padding:5px; }
        """
