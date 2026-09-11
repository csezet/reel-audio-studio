from __future__ import annotations

import importlib
import os
import shutil
import sys
from pathlib import Path

from PySide6.QtCore import QProcess, QSettings, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout

from reel_audio.engine.deepfilter import deepfilter_available, deepfilter_install_path
from reel_audio.engine.tools import find_executable
from reel_audio.engine.vad import (
    SILERO_MODEL_SHA256, SILERO_MODEL_URL, silero_available, silero_model_install_path,
)
from .vector_icons import make_icon
from .widgets import CaptionButton, ToggleSwitch, ui_animations_enabled

class SettingsDialog(QDialog):
    """Glass settings sheet with live component installation controls."""

    INSTALLS = {
        "DeepFilterNet": [],
        "Silero VAD": [],
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

    def _ai_install_steps(self, component: str) -> list[list[str]]:
        # Keep AI dependencies reproducible. Torch 2.9.1 is pinned for DeepFilterNet. Silero uses a pure ONNX path
        # and therefore does not install PyTorch at all.
        nvidia = bool(shutil.which("nvidia-smi"))
        torch_index = "https://download.pytorch.org/whl/cu126" if nvidia else "https://download.pytorch.org/whl/cpu"
        torch_step = [
            "-m", "pip", "install", "--disable-pip-version-check", "--no-input",
            "torch==2.9.1", "torchaudio==2.9.1", "--index-url", torch_index,
        ]
        if component == "DeepFilterNet":
            if os.name == "nt":
                # Prefer the upstream precompiled Windows binary: no PyTorch, no
                # Python ABI coupling, and it also works for a frozen desktop build.
                dst = deepfilter_install_path()
                download_code = (
                    "from pathlib import Path; import hashlib,json,urllib.request; "
                    "api='https://api.github.com/repos/Rikorose/DeepFilterNet/releases/tags/v0.5.6'; "
                    "req=urllib.request.Request(api,headers={'User-Agent':'ReelAudioStudio'}); "
                    "rel=json.load(urllib.request.urlopen(req)); "
                    "name='deep-filter-0.5.6-x86_64-pc-windows-msvc.exe'; "
                    "a=next(x for x in rel['assets'] if x['name']==name); "
                    f"d=Path({str(dst)!r}); d.parent.mkdir(parents=True,exist_ok=True); t=d.with_suffix('.exe.part'); "
                    "req=urllib.request.Request(a['browser_download_url'],headers={'User-Agent':'ReelAudioStudio'}); "
                    "urllib.request.urlretrieve(req.full_url,t); data=t.read_bytes(); "
                    "assert len(data)>20_000_000 and data[:2]==b'MZ','Invalid DeepFilter binary'; "
                    "dg=a.get('digest') or ''; "
                    "assert (not dg.startswith('sha256:')) or hashlib.sha256(data).hexdigest()==dg.split(':',1)[1], 'SHA256 mismatch'; "
                    "t.replace(d); print('DeepFilter installed:',d)"
                )
                return [["-c", download_code]]
            return [
                torch_step,
                ["-m", "pip", "install", "--disable-pip-version-check", "--no-input", "numpy<2", "deepfilternet==0.5.6"],
            ]
        if component == "Silero VAD":
            dst = silero_model_install_path()
            # Silero's ONNX path does not require PyTorch in Reel Audio Studio:
            # FFmpeg supplies PCM I/O and our own stateful wrapper handles post-processing.
            download_code = (
                "from pathlib import Path; import hashlib, urllib.request; "
                f"u={SILERO_MODEL_URL!r}; d=Path({str(dst)!r}); "
                "d.parent.mkdir(parents=True, exist_ok=True); t=d.with_suffix('.onnx.part'); "
                "urllib.request.urlretrieve(u, t); "
                "h=hashlib.sha256(t.read_bytes()).hexdigest(); "
                f"assert h == {SILERO_MODEL_SHA256!r}, 'SHA256 mismatch'; "
                "t.replace(d); print('Silero ONNX model installed:', d)"
            )
            return [
                ["-m", "pip", "install", "--disable-pip-version-check", "--no-input", "numpy<2", "onnxruntime==1.29.0"],
                ["-c", download_code],
            ]
        return []

    def _install(self, component: str) -> None:
        if self._process is not None:
            return
        python = self._python_for_install()
        if not python:
            self._set_feedback("Не найден Python для установки модулей. Запустите проект через run_windows.bat или установите AI перед сборкой EXE.", error=True)
            return

        self._install_component = component
        self._install_steps = [list(step) for step in self._ai_install_steps(component)]
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


