@echo off
setlocal

if not defined PYTHON (set PYTHON=python)
if not defined VENV_DIR (set "VENV_DIR=%~dp0%.venv")

:ask_flash_attn
set /p "FLASH_ATTN=Does your hardware support flash attention 2? (nvidia 30xx GPU, Ampere generation or later) [y/N] "


:check_venv
dir "%VENV_DIR%" > NUL 2> NUL
if %ERRORLEVEL% == 0 goto :activate_venv

:create_venv
echo Creating virtual environment in '%VENV_DIR%'
%PYTHON% -m venv "%VENV_DIR%"
if %ERRORLEVEL% == 0 goto :activate_venv
echo Couldn't create virtual environment
goto :end_error

:activate_venv
echo Activating virtual environment: %VENV_DIR%
set PYTHON="%VENV_DIR%\Scripts\python.exe"


:install_dependencies
echo.
echo Installing pytorch
%PYTHON% -m pip install -r requirements-pytorch.txt

echo.
echo Installing base requirements
%PYTHON% -m pip install -r requirements.txt

echo.
echo Installing llama-cpp-python
%PYTHON% -m pip install -r requirements-llamacpp.txt

echo.
echo Installing onnxruntime-gpu
%PYTHON% -m pip install -r requirements-onnx.txt

if /i "%FLASH_ATTN%"=="y" (
    echo.
    echo Installing flash attention
    rem %PYTHON% -m pip install flash_attn --no-build-isolation
    %PYTHON% -m pip install -r requirements-flashattn.txt
)


:end_success
echo.
echo Setup finished
goto:end

:end_error
echo.
echo Setup failed
goto:end

:end
pause
endlocal
