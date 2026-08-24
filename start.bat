@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ===================================================
echo  SeedanceMini v2 - Starting
echo ===================================================
echo.

if not exist ".venv\Scripts\python.exe" (
  echo The virtual environment is missing.
  echo Run setup.bat first, then run start.bat again.
  echo.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" -c "import uvicorn" >nul 2>nul
if errorlevel 1 (
  echo Uvicorn is not installed in the project environment.
  echo Run setup.bat again to install all dependencies.
  echo.
  pause
  exit /b 1
)

echo Local address: http://127.0.0.1:8000
echo LAN access: use http://YOUR-IP:8000
echo Keep this window open while using the app.
echo To stop the server, double-click stop.bat.
echo.
start "" "http://127.0.0.1:8000"
".venv\Scripts\python.exe" -m uvicorn web.app:app --host 0.0.0.0 --port 8000

echo.
echo The server has stopped.
pause
