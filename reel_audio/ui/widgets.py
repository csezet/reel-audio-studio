from __future__ import annotations

from PySide6.QtCore import QEvent, QEasingCurve, Property, QPropertyAnimation, QRectF, QSettings, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QLinearGradient, QMouseEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractButton, QButtonGroup, QComboBox, QFrame, QHBoxLayout, QLabel, QListView,
    QPushButton, QSizePolicy, QSlider, QVBoxLayout, QWidget,
)

from .vector_icons import draw_vector_icon, make_icon, make_state_icon

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
        # v16: slightly denser glass. Keep only a very faint hint of the desktop visible.
        # Alpha is intentionally changed only on the background plate, not on
        # the entire window, so text/icons/controls stay fully opaque and crisp.
        gradient.setColorAt(0.0, QColor(55, 66, 77, 250))
        gradient.setColorAt(0.52, QColor(37, 46, 55, 249))
        gradient.setColorAt(1.0, QColor(27, 35, 42, 250))
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


