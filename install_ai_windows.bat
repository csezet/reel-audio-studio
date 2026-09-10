@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Run run_windows.bat first.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
pip install -r requirements-ai.txt
python -c "import silero_vad; print('Silero VAD: OK')"
where deepFilter >nul 2>nul && echo DeepFilterNet CLI: OK || echo DeepFilterNet CLI not found in PATH
endlocal
