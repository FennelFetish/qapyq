@echo off
setlocal

if not defined PYTHON (
    set "PYTHON=python"
)

if not defined VENV_DIR (
    set "VENV_DIR=%~dp0.venv"
)


if not exist "%VENV_DIR%" (
    echo Creating virtual environment: '%VENV_DIR%'
    %PYTHON% -m venv "%VENV_DIR%"
)


set PYTHON="%VENV_DIR%\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo Couldn't create virtual environment
    echo Setup failed
    goto :end
)

echo Active virtual environment: '%VENV_DIR%'
%PYTHON% --version
echo.

cd /d "%~dp0"
%PYTHON% main_setup.py

:end
endlocal
pause
