@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  py -3 -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
pyinstaller --noconfirm --clean --windowed --onedir ^
  --name ReelAudioStudio ^
  --icon "assets\reel_audio.ico" ^
  --add-data "assets;assets" ^
  --add-data "bin;bin" ^
  main.py
if errorlevel 1 exit /b 1
echo.
echo Build ready in dist\ReelAudioStudio\
endlocal
