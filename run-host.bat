@echo off
setlocal

if not defined VENV_DIR (
    set "VENV_DIR=%~dp0.venv"
)

set "PYTHON=%VENV_DIR%\Scripts\python.exe"
if not exist "%PYTHON%" (
    exit 1
)

set NO_ALBUMENTATIONS_UPDATE="1"
set YOLO_OFFLINE="True"

cd /d "%~dp0"
%PYTHON% main_host.py %*

endlocal
