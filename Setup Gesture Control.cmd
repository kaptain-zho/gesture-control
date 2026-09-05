@echo off
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
    python setup_app.py
) else (
    py -3.12 setup_app.py
)
pause
