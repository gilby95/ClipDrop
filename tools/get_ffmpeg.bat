@echo off
rem Downloads ffmpeg + ffprobe (shared build: small exes + one set of DLLs) into ClipDrop\bin
cd /d "%~dp0.."
if exist "bin\ffmpeg.exe" if exist "bin\ffprobe.exe" exit /b 0
echo Downloading ffmpeg (about 90 MB)...
if not exist bin mkdir bin
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop'; $z=Join-Path $env:TEMP 'clipdrop_ffmpeg.zip'; $d=Join-Path $env:TEMP 'clipdrop_ffmpeg';" ^
  "Invoke-WebRequest 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl-shared.zip' -OutFile $z;" ^
  "if (Test-Path $d) { Remove-Item $d -Recurse -Force }; Expand-Archive $z $d;" ^
  "Get-ChildItem $d -Recurse -Include ffmpeg.exe,ffprobe.exe,*.dll | Copy-Item -Destination 'bin';" ^
  "Remove-Item $z,$d -Recurse -Force" || exit /b 1
echo ffmpeg ready.
