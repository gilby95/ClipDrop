@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Setting up ClipDrop for the first time...
  py -3 -m venv .venv || python -m venv .venv || (echo Python 3.10+ is needed: https://www.python.org/downloads/ & pause & exit /b 1)
  ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt || (pause & exit /b 1)
)
if not exist "bin\ffmpeg.exe" call "%~dp0tools\get_ffmpeg.bat" || (pause & exit /b 1)
start "" ".venv\Scripts\pythonw.exe" -m clipdrop
