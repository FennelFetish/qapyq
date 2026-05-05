@echo off
setlocal

if not defined VENV_DIR (
    set "VENV_DIR=%~dp0.venv"
)

rem Use pythonw executable to hide console - pythonw doesn't connect pipes
set "PYTHON=%VENV_DIR%\Scripts\pythonw.exe"

if not exist "%PYTHON%" (
    echo Virtual environment not found. Please run setup.bat first.
    pause
    exit /b 1
)

cd /d "%~dp0"

rem Create fake pipes so inference subprocess can forward error channel
start "" /B %PYTHON% main.py %* > NUL 2>&1

endlocal
