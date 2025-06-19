@echo off
setlocal

if not defined VENV_DIR (set "VENV_DIR=%~dp0%.venv")

:check_venv
dir "%VENV_DIR%" > NUL 2> NUL
if not %ERRORLEVEL% == 0 goto :end

:activate_venv
set PYTHON="%VENV_DIR%\Scripts\python.exe"


:launch
cd /d "%~dp0%"
%PYTHON% main_host.py "%1"

:end
endlocal
