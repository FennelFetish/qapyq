@echo off
setlocal

if not defined VENV_DIR (
    set "VENV_DIR=%~dp0.venv"
)

set "PYTHON=%VENV_DIR%\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo Virtual environment not found. Please run setup.bat first.
    goto :end
)

echo Using environment: '%VENV_DIR%'

cd /d "%~dp0"
%PYTHON% main.py %*

:end
endlocal
pause
