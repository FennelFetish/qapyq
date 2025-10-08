@echo off
setlocal

if not defined PYTHON (set PYTHON=python)
if not defined VENV_DIR (set "VENV_DIR=%~dp0%.venv")

%PYTHON% --version

:check_venv
dir "%VENV_DIR%" > NUL 2> NUL
if %ERRORLEVEL% == 0 goto :activate_venv

:create_venv
echo Creating virtual environment: '%VENV_DIR%'
%PYTHON% -m venv "%VENV_DIR%"
if %ERRORLEVEL% == 0 goto :activate_venv
echo Couldn't create virtual environment
goto :end_error

:activate_venv
set PYTHON="%VENV_DIR%\Scripts\python.exe"
echo Active virtual environment: '%VENV_DIR%'
echo.

:launch_setup
cd /d "%~dp0%"
%PYTHON% main_setup.py
goto :end

:end_error
echo.
echo Setup failed

:end
pause
endlocal
