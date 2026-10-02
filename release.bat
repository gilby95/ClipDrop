@echo off
rem Publish an update:  release.bat "What's new"
cd /d "%~dp0"
".venv\Scripts\python.exe" tools\release.py %*
pause
