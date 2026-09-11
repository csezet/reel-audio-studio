from __future__ import annotations

import importlib
import logging
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
from .workers import ExportThread, ProcessingThread, WaveformThread

log = logging.getLogger(__name__)

SUPPORTED = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".wav", ".mp3", ".m4a", ".flac", ".aac"}


from .settings_dialog import SettingsDialog
from .widgets import (
    AnimatedPresetButton, AnimatedPrimaryButton, CaptionButton, DropFrame, FileAddButton,
    GlassComboBox, GlassShell, GlassSlider, IconBadge, ResizeHandle, SettingCard, TitleBar, ToggleSwitch,
)

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
        self.export_thread: ExportThread | None = None
        self.wave_thread: WaveformThread | None = None
        self._wave_request_id = 0
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
        self.player.errorOccurred.connect(self._on_media_error)

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
        self.format_combo = GlassComboBox(); self.format_combo.addItems(["MP4 (H.264)"]); self.format_combo.currentTextChanged.connect(self._on_export_format_changed); export_layout.addWidget(self.format_combo)
        self.quality_combo = GlassComboBox(); self.quality_combo.addItems(["Без доп. перекодирования", "Высокое", "Стандартное", "Компактное"]); export_layout.addWidget(self.quality_combo)
        self.export_btn = QPushButton("Экспорт"); self.export_btn.setObjectName("ExportButton"); self.export_btn.setIcon(make_icon("upload", "#1e252b")); self.export_btn.setIconSize(QSize(21,21)); self.export_btn.setEnabled(False); self.export_btn.clicked.connect(self.export_result); export_layout.addWidget(self.export_btn)
        layout.addWidget(export_panel)

        # Footer / progress
        footer = QHBoxLayout(); footer.setSpacing(7)
        creator = QLabel("csezet"); creator.setObjectName("CreatorTag"); footer.addWidget(creator)
        creator_sep = QLabel("•"); creator_sep.setObjectName("FooterText"); footer.addWidget(creator_sep)
        self.status = QLabel("Готов к работе"); self.status.setObjectName("FooterText"); footer.addWidget(self.status)
        self.progress = QProgressBar(); self.progress.setRange(0,100); self.progress.setValue(0); self.progress.setFixedWidth(145); self.progress.setFixedHeight(5); self.progress.setTextVisible(False); self.progress.setVisible(False); footer.addWidget(self.progress)
        self.cancel_job_btn = QPushButton("Отмена"); self.cancel_job_btn.setObjectName("FooterCancel"); self.cancel_job_btn.setVisible(False); self.cancel_job_btn.clicked.connect(self.cancel_active_job); footer.addWidget(self.cancel_job_btn)
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
            self.enhance_btn.setEnabled(not running)

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
        self._configure_export_options(info)
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
        self.enhance_btn.setEnabled(True)
        self.after_btn.setEnabled(False); self.export_btn.setEnabled(False); self.before_btn.setChecked(True); self.after_btn.setChecked(False)
        self.status.setText("Строю waveform…"); self._load_waveform(str(p))

    def clear_selected_file(self):
        """Detach the current media from the project without deleting it on disk."""
        if self.processing_thread and self.processing_thread.isRunning():
            self.status.setText("Дождитесь окончания обработки перед сменой файла")
            return

        for thread in self.findChildren(WaveformThread):
            if thread.isRunning():
                thread.requestInterruption()
        self._wave_request_id += 1

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
        self.enhance_btn.setEnabled(True)
        self.status.setText("Файл убран  •  выберите новый ролик или аудио")

    def _load_waveform(self, path: str):
        for thread in self.findChildren(WaveformThread):
            if thread.isRunning():
                thread.requestInterruption()
        self._wave_request_id += 1
        request_id = self._wave_request_id
        duration = None
        if self.input_path and Path(path) == self.input_path and self._last_info:
            duration = float(self._last_info.get("duration") or 0.0)
        self.wave_thread = WaveformThread(path, request_id, duration, self)
        self.wave_thread.done.connect(self._wave_ready)
        self.wave_thread.failed.connect(self._wave_failed)
        self.wave_thread.start()

    def _wave_ready(self, request_id: int, peaks: list):
        if request_id != self._wave_request_id:
            return
        self.waveform.set_peaks(peaks)
        self.status.setText("Готов к обработке")

    def _wave_failed(self, request_id: int, error: str):
        if request_id == self._wave_request_id:
            self.status.setText(f"Waveform: {error}")

    # ---- presets / processing ----------------------------------------------------------
    def apply_preset(self, name: str):
        presets = {"Auto":(70,60,50,True,True,-14),"Voice Clean":(58,55,48,False,True,-14),"Street / Car":(82,62,58,True,True,-14),"Natural":(28,30,32,False,True,-16),"Voice + Music":(38,42,40,False,True,-14),"Podcast":(48,52,46,True,True,-16)}
        n,p,c,pauses,normalize,lufs = presets.get(name,presets["Auto"])
        self.noise_card.set_value(n); self.presence_card.set_value(p); self.compression_card.set_value(c)
        self.noise_card.toggle.setChecked(n>0); self.presence_card.toggle.setChecked(p>0); self.compression_card.toggle.setChecked(c>0)
        self.pause_card.toggle.setChecked(pauses); self.normalize_card.toggle.setChecked(normalize); self.lufs.setCurrentText(f"{lufs} LUFS")
        if name == "Voice + Music":
            self.deepfilter.setChecked(False)
            self.deepfilter.setToolTip("DeepFilterNet не применяется к полному музыкальному миксу без разделения stem-ов.")
        else:
            self.deepfilter.setToolTip("" if deepfilter_available() else "Установите DeepFilterNet через Настройки")
        if name in self.preset_buttons: self.preset_buttons[name].setChecked(True)

    def _settings(self) -> ProcessingSettings:
        keep_ms = int(self.keep_pause.currentText().split()[0])
        preset = next((k for k,b in self.preset_buttons.items() if b.isChecked()),"Auto")
        return ProcessingSettings(
            preset=preset,
            noise_removal=self.noise_card.value() if self.noise_card.toggle.isChecked() else 0,
            voice_presence=self.presence_card.value() if self.presence_card.toggle.isChecked() else 0,
            compression=self.compression_card.value() if self.compression_card.toggle.isChecked() else 0,
            remove_pauses=self.pause_card.toggle.isChecked(), keep_pause_seconds=keep_ms/1000.0,
            target_lufs=float(self.lufs.currentText().split()[0]), auto_normalize=self.normalize_card.toggle.isChecked(),
            ai_deepfilter=self.deepfilter.isChecked() and preset != "Voice + Music", ai_vad=self.ai_vad.isChecked(),
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
        self._set_busy(True); self.progress.setValue(0); self.processing_thread = ProcessingThread(str(self.input_path),str(preview),self._settings(),self)
        self.processing_thread.stage.connect(self.status.setText)
        self.processing_thread.progress.connect(self.progress.setValue)
        self.processing_thread.done.connect(self._process_done)
        self.processing_thread.failed.connect(self._process_failed)
        self.processing_thread.cancelled.connect(self._process_cancelled)
        self.processing_thread.start()

    def _set_busy(self, busy: bool):
        self.progress.setVisible(busy)
        self.cancel_job_btn.setVisible(busy)
        self.enhance_btn.setEnabled(not busy)
        self.remove_file_btn.setEnabled(not busy)
        self.export_btn.setEnabled(not busy and self.processed_path is not None)
        self.open_btn.setEnabled(not busy)
        self.add_file_btn.setEnabled(not busy)

    def cancel_active_job(self):
        if self.processing_thread and self.processing_thread.isRunning():
            self.status.setText("Отменяю обработку…")
            self.processing_thread.requestInterruption()
            self.cancel_job_btn.setEnabled(False)
            return
        if self.export_thread and self.export_thread.isRunning():
            self.status.setText("Отменяю экспорт…")
            self.export_thread.requestInterruption()
            self.cancel_job_btn.setEnabled(False)

    def _process_cancelled(self):
        self.cancel_job_btn.setEnabled(True)
        self._set_busy(False)
        self.progress.setValue(0)
        self.status.setText("Обработка отменена")

    def _process_done(self, path: str):
        self.cancel_job_btn.setEnabled(True)
        self.processed_path = Path(path); self.after_btn.setEnabled(True); self.export_btn.setEnabled(True); self._set_busy(False); self.progress.setValue(100); self.status.setText("Готово  •  сравните До / После"); self.switch_source(True)

    def _process_failed(self, error: str):
        log.error("processing failed: %s", error)
        self.cancel_job_btn.setEnabled(True)
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

    def _on_media_error(self, error, error_string: str):
        if not error_string:
            return
        log.warning("QMediaPlayer error %s: %s", error, error_string)
        self.status.setText(f"Ошибка проигрывателя: {error_string}")
        self.file_hint.setText("Не удалось воспроизвести этот поток • обработка через FFmpeg всё ещё может работать")

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

    def _configure_export_options(self, info: dict):
        self.format_combo.blockSignals(True)
        self.format_combo.clear()
        if info.get("has_video"):
            self.format_combo.addItems(["MP4 (H.264)"])
        else:
            self.format_combo.addItems(["M4A (AAC)", "WAV (PCM)"])
        self.format_combo.blockSignals(False)
        self._on_export_format_changed(self.format_combo.currentText())

    def _on_export_format_changed(self, format_name: str):
        current = self.quality_combo.currentText() if hasattr(self, "quality_combo") else ""
        self.quality_combo.blockSignals(True)
        self.quality_combo.clear()
        if format_name.startswith("WAV"):
            self.quality_combo.addItem("PCM 24-bit")
        else:
            self.quality_combo.addItems(["Без доп. перекодирования", "Высокое", "Стандартное", "Компактное"])
            if current in {"Без доп. перекодирования", "Высокое", "Стандартное", "Компактное"}:
                self.quality_combo.setCurrentText(current)
        self.quality_combo.blockSignals(False)

    def export_result(self):
        if not self.processed_path or (self.export_thread and self.export_thread.isRunning()):
            return
        format_name = self.format_combo.currentText()
        quality = self.quality_combo.currentText()
        if format_name.startswith("MP4"):
            default, file_filter = "enhanced_reel.mp4", "MP4 (*.mp4)"
        elif format_name.startswith("WAV"):
            default, file_filter = "enhanced_audio.wav", "WAV (*.wav)"
        else:
            default, file_filter = "enhanced_audio.m4a", "M4A (*.m4a)"
        path, _ = QFileDialog.getSaveFileName(self, "Экспорт", default, file_filter)
        if not path:
            return
        self._set_busy(True)
        self.progress.setValue(0)
        self.export_thread = ExportThread(str(self.processed_path), path, format_name, quality, self)
        self.export_thread.stage.connect(self.status.setText)
        self.export_thread.progress.connect(self.progress.setValue)
        self.export_thread.done.connect(self._export_done)
        self.export_thread.failed.connect(self._export_failed)
        self.export_thread.cancelled.connect(self._export_cancelled)
        self.export_thread.start()

    def _export_done(self, path: str):
        self.cancel_job_btn.setEnabled(True)
        self._set_busy(False)
        self.progress.setValue(100)
        self.status.setText(f"Экспортировано: {Path(path).name}")

    def _export_failed(self, error: str):
        log.error("export failed: %s", error)
        self.cancel_job_btn.setEnabled(True)
        self._set_busy(False)
        self.status.setText("Ошибка экспорта")
        QMessageBox.critical(self, "Ошибка экспорта", error)

    def _export_cancelled(self):
        self.cancel_job_btn.setEnabled(True)
        self._set_busy(False)
        self.progress.setValue(0)
        self.status.setText("Экспорт отменён")

    def closeEvent(self, event):
        self.player.stop()
        threads = [self.processing_thread, self.export_thread, *self.findChildren(WaveformThread)]
        threads = [thread for i, thread in enumerate(threads) if thread is not None and thread not in threads[:i]]
        for thread in threads:
            if thread and thread.isRunning():
                thread.requestInterruption()
        for thread in threads:
            if thread and thread.isRunning() and not thread.wait(5000):
                self.status.setText("Завершаю фоновую операцию…")
                event.ignore()
                return
        shutil.rmtree(self._temp_root, ignore_errors=True)
        super().closeEvent(event)

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
        QPushButton#FooterCancel { background:rgba(112,67,67,82); border:1px solid rgba(226,167,167,54); border-radius:6px; color:#dfc5c5; padding:3px 9px; font-size:9px; }
        QPushButton#FooterCancel:hover { background:rgba(143,77,77,118); border-color:rgba(238,181,181,78); color:#f0d8d8; }
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
