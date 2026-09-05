@echo off
cd /d "%~dp0"
if exist "%~dp0.venv\Scripts\pythonw.exe" (
    start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0app.py"
    exit /b
)
if exist "%~dp0..\..\work\gesture-venv\Scripts\pythonw.exe" (
    start "" "%~dp0..\..\work\gesture-venv\Scripts\pythonw.exe" "%~dp0app.py"
    exit /b
)
echo Run Setup Gesture Control.cmd first.
pause
