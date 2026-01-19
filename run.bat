@echo off
setlocal

if not defined VENV_DIR (set "VENV_DIR=%~dp0%.venv")

:check_venv
dir "%VENV_DIR%" > NUL 2> NUL
if %ERRORLEVEL% == 0 goto :activate_venv
echo Virtual environment not found. Please run setup.bat first.
goto :end

rem Use pythonw executable to hide console
:activate_venv
echo Activating virtual environment: %VENV_DIR%
set PYTHON="%VENV_DIR%\Scripts\pythonw.exe"
echo Using Python %PYTHON%

:launch
cd /d "%~dp0%"
start "" /B %PYTHON% main.py %* > "last.log" 2>&1

:end
endlocal
