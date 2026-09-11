@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  py -3 -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
pyinstaller --noconfirm --clean ReelAudioStudio.spec
if errorlevel 1 exit /b 1
echo.
echo Build ready in dist\ReelAudioStudio\
endlocal
