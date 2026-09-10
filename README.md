# 🎙️ Reel Audio Studio — Glass UI v9 (Soft Glass)

<p align="center">
  <b>Нативное Windows-приложение для локальной обработки и улучшения звука в Reels, Shorts и TikTok.</b><br>
  Построено на <b>Qt Widgets / PySide6</b> с мягким стеклянным интерфейсом (Soft Glass) и нативными анимациями Windows 11 (DWM). Никакого браузера, Electron или WebView.
</p>

<p align="center">
  <a href="https://github.com/csezet/reel-audio-studio/releases/download/v1.3.0/ReelAudioStudio_GlassUI_v9_SoftGlass.zip">
    <img src="https://img.shields.io/badge/СКАЧАТЬ%20ZIP-v1.3.0%20(Прямая%20ссылка)-2ea44f?style=for-the-badge&logo=windows&logoColor=white" alt="Скачать релиз ZIP" height="42">
  </a>
  &nbsp;&nbsp;
  <a href="https://github.com/csezet/reel-audio-studio/archive/refs/heads/main.zip">
    <img src="https://img.shields.io/badge/СКАЧАТЬ%20РЕПОЗИТОРИЙ-ZIP%20Архив-0969da?style=for-the-badge&logo=github&logoColor=white" alt="Скачать исходный код" height="42">
  </a>
  &nbsp;&nbsp;
  <a href="https://github.com/csezet/reel-audio-studio/releases/latest">
    <img src="https://img.shields.io/badge/СТРАНИЦА%20РЕЛИЗОВ-GitHub%20Releases-6e5494?style=for-the-badge&logo=git&logoColor=white" alt="Страница релизов" height="42">
  </a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%20%7C%203.11-3776AB?style=flat&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/GUI-PySide6%20(Qt%206)-41CD52?style=flat&logo=qt&logoColor=white" alt="PySide6">
  <img src="https://img.shields.io/badge/Платформа-Windows%2010%20%2F%2011-0078D6?style=flat&logo=windows&logoColor=white" alt="Windows">
  <img src="https://img.shields.io/badge/Движок-FFmpeg-007808?style=flat&logo=ffmpeg&logoColor=white" alt="FFmpeg">
</p>

---

## ✨ Возможности

- **Широкая поддержка форматов**: MP4, MOV, MKV, AVI, WebM, WAV, MP3, M4A, FLAC, AAC.
- **Интерфейс Glass UI v9 (Soft Glass)**:
  - Комфортная плотность фона (90–93% непрозрачности) — рабочий стол виден лёгким благородным оттенком, а весь текст и интерфейс читаются идеально.
  - Нативные плавные анимации сворачивания, восстановления и разворачивания окна Windows 11 через перехват `WM_NCCALCSIZE` и Win32 `ShowWindow`.
  - Кастомная отрисовка `GlassShell` с антиалиасингом (`QPainterPath`) строго по скруглённому контуру окна (без паразитных теней и серых полос).
  - Кастомный заголовок окна со стандартными кнопками (свернуть, развернуть, закрыть), поддержкой разворачивания по двойному клику и нативного перетаскивания.
  - Кастомные стеклянные слайдеры `GlassSlider` без артефактов масштабирования DPI.
  - Плавное изменение размера окна по системным границам.
  - История недавних файлов (Recent Files).
- **Превью и контроль звука**:
  - Интерактивная визуализация аудиоволны (Waveform) со шкалой времени и курсором воспроизведения.
  - Переключение **До / После** (Before / After) в реальном времени.
- **Студийная цепочка обработки (FFmpeg)**:
  - Срез инфранизкого гула (Highpass 70 Гц).
  - Интеллектуальное спектральное шумоподавление FFT (`afftdn`).
  - Эквалайзер присутствия голоса (Voice Presence EQ ~3 кГц) для чёткости речи.
  - Мягкая динамическая компрессия (`acompressor`).
  - Нормализация громкости по стандарту EBU R128 (`loudnorm`: выбор -16, -14, -12 LUFS).
  - Пиковый лимитер (`alimiter`).
- **Синхронное удаление пауз**:
  - Автоматическое нахождение тишины и вырезание пауз **одновременно из видео и аудио** (синхронизация губ и таймлайн видео сохраняются идеально).
- **Опциональные нейросетевые модули (AI)**:
  - **DeepFilterNet** — удаление шумов через модель глубокого обучения.
  - **Silero VAD** — нейросетевой детектор голосовой активности для хирургически точного определения пауз.
- **Экспорт**: сохранение готового видео в MP4 или аудиодорожки в M4A.

---

## 🚀 Быстрый старт

### 1. Скачивание
Нажмите большую зелёную кнопку **[Скачать ZIP (v1.0.0)](https://github.com/csezet/reel-audio-studio/releases/download/v1.0.0/ReelAudioStudio_GlassUI_v5_Borderless.zip)** вверху страницы и распакуйте архив в удобное место на вашем ПК.

### 2. FFmpeg
Приложению требуются `ffmpeg.exe` и `ffprobe.exe`.

- Если FFmpeg уже установлен в вашей системе и прописан в PATH — приложение подхватит его автоматически.
- Либо просто скопируйте файлы `ffmpeg.exe` и `ffprobe.exe` в папку `bin/` внутри проекта.

### 3. Запуск в 1 клик
Дважды щёлкните по файлу:

```bat
run_windows.bat
```

Скрипт автоматически:
1. Создаст локальное виртуальное окружение `.venv` (Python 3.10 / 3.11).
2. Установит необходимые библиотеки из `requirements.txt` (PySide6).
3. Запустит графический интерфейс приложения.

---

## 🛠️ Ручной запуск через консоль

Если вы предпочитаете запускать через командную строку:

```bat
# Создание виртуального окружения
py -3.11 -m venv .venv

# Активация окружения
.venv\Scripts\activate

# Установка зависимостей
pip install -r requirements.txt

# Запуск приложения
python main.py
```

---

## 🧠 Дополнительные AI-модули (опционально)

По умолчанию удаление шума работает через встроенный быстрый фильтр FFmpeg `afftdn`, а поиск пауз — через `silencedetect`.

Если вам требуется нейросетевая обработка голоса (**DeepFilterNet**) и нейросетевой детектор пауз (**Silero VAD**), запустите:

```bat
install_ai_windows.bat
```

Или вручную в активированном окружении:

```bat
pip install -r requirements-ai.txt
```

---

## 📦 Сборка в автономный `.exe`

Вы можете собрать приложение в виде папки с готовым исполняемым файлом без необходимости устанавливать Python:

1. Убедитесь, что `ffmpeg.exe` и `ffprobe.exe` лежат в папке `bin/`.
2. Запустите:

```bat
build_windows.bat
```

Результат сборки появится в папке:
```text
dist\ReelAudioStudio\ReelAudioStudio.exe
```

Сборка автоматически вшивает фирменную иконку `assets\reel_audio.ico` и упаковывает все необходимые ассеты.

---

## 📊 Граф обработки звука

```text
Входное видео / аудио
   │
   ├─► Опционально: Silero VAD / FFmpeg silencedetect
   │      └── Синхронная нарезка пауз (видео + аудио)
   │
   ├─► Опционально: нейросеть DeepFilterNet
   │
   ├─► Highpass 70 Гц
   ├─► FFmpeg afftdn (если выключен DeepFilterNet)
   ├─► Эквалайзер присутствия голоса (~3 кГц)
   ├─► FFmpeg acompressor
   ├─► Опционально: FFmpeg loudnorm (-16 / -14 / -12 LUFS)
   ├─► Ресемплинг в 48 кГц
   └─► FFmpeg alimiter (пиковый лимитер)
          │
          ▼
   Финальный MP4 / M4A
```

---

## 🧪 Запуск тестов

Тестирование графа обработки не требует запущенного PySide6:

```bat
python -m unittest discover -s tests -v
```

---

## 💻 Технические детали Glass UI

- Приложение разработано на чистом **Qt Widgets (PySide6)** без использования веб-движков, Electron или CEF.
- Для безрамочного оформления используется `Qt::FramelessWindowHint`.
- Перемещение и изменение размеров окна вызывают нативные методы ОС `QWindow::startSystemMove()` и `QWindow::startSystemResize()`.
- На **Windows 11 (сборка 22621+)** модуль `windows_effects.py` вызывает функцию DWM API с атрибутом `DWMWA_SYSTEMBACKDROP_TYPE` и параметром `DWMSBT_TRANSIENTWINDOW` (Desktop Acrylic), а также включает тёмную тему и скругление углов.
- На более ранних версиях Windows автоматически включается полупрозрачный матовый Qt-фоллбэк.

---

## 📄 Лицензия

Распространяется под свободной лицензией. Подробнее о сторонних библиотеках см. в [docs/THIRD_PARTY.md](docs/THIRD_PARTY.md).