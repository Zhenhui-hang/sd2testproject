@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ===================================================
echo  SeedanceMini v2 - Windows Setup
echo ===================================================
echo.

echo [1/5] Checking Python 3.10...
py -3.10 --version >nul 2>nul
if errorlevel 1 (
  echo Python 3.10 is not installed. Trying to install it...
  py install 3.10
  if errorlevel 1 (
    echo.
    echo Python 3.10 could not be installed automatically.
    echo Run this command first: py install 3.10
    echo Then run setup.bat again.
    pause
    exit /b 1
  )
)
py -3.10 --version
echo.

echo [2/5] Checking FFmpeg...
where ffmpeg >nul 2>nul
if not errorlevel 1 goto ffmpeg_ok
if exist "%~dp0tools\ffmpeg.exe" goto ffmpeg_ok
echo FFmpeg was not found. Quick Cut will be unavailable.
echo Setup will continue because FFmpeg is optional.
echo You can install it later from: https://www.gyan.dev/ffmpeg/builds/
goto ffmpeg_done

:ffmpeg_ok
echo FFmpeg is ready.

:ffmpeg_done
echo.

echo [3/5] Preparing the Python 3.10 virtual environment...
if not exist ".venv\Scripts\python.exe" goto create_venv
".venv\Scripts\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 10) else 1)" >nul 2>nul
if not errorlevel 1 goto venv_ready
echo Existing virtual environment is not Python 3.10. Recreating it...
rmdir /s /q ".venv"

:create_venv
py -3.10 -m venv .venv
if errorlevel 1 (
  echo Failed to create the virtual environment.
  pause
  exit /b 1
)

:venv_ready
".venv\Scripts\python.exe" --version
echo.

echo [4/5] Installing dependencies. This may take several minutes...
".venv\Scripts\python.exe" -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 goto install_failed
".venv\Scripts\python.exe" -m pip install --upgrade -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 goto install_failed
".venv\Scripts\python.exe" -c "from volcenginesdkarkruntime import Ark; c=Ark(api_key='setup-check'); assert hasattr(c, 'content_generation'), 'Ark SDK missing content_generation'"
if errorlevel 1 (
  echo [ERROR] Ark SDK does not support Seedance video generation.
  echo Please run setup.bat again after checking the network.
  goto install_failed
)
echo.

echo [5/5] Setup completed successfully.
echo Double-click start.bat to start SeedanceMini v2.
echo Local address: http://127.0.0.1:8000
echo.
pause
exit /b 0

:install_failed
echo.
echo Dependency installation failed. Check your network and run setup.bat again.
pause
exit /b 1
