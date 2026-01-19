@echo off
setlocal

if not defined VENV_DIR (set "VENV_DIR=%~dp0%.venv")

:check_venv
dir "%VENV_DIR%" > NUL 2> NUL
if %ERRORLEVEL% == 0 goto :activate_venv
echo Virtual environment not found. Please run setup.bat first.
goto :end

:activate_venv
echo Activating virtual environment: %VENV_DIR%
set PYTHON="%VENV_DIR%\Scripts\python.exe"
echo Using Python %PYTHON%

:launch
cd /d "%~dp0%"
%PYTHON% main.py %*

:end
endlocal
pause
