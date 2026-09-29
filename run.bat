@echo off
rem Video Studio - arranque en Windows.  run.bat [--port 8470] [--no-browser] [--install-engine] [--rebuild] [--lan]
setlocal
cd /d "%~dp0"
set "PATH=%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin;%APPDATA%\npm;%PATH%"
where uv >nul 2>nul
if errorlevel 1 (
  echo [video-studio] Falta uv: powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 ^| iex"
  pause
  exit /b 1
)
if not exist "back\.venv\Scripts\python.exe" uv venv back\.venv --python 3.12
"back\.venv\Scripts\python.exe" launcher.py %*
if errorlevel 1 pause
endlocal
