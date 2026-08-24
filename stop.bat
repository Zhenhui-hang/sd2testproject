@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ===================================================
echo  SeedanceMini v2 - Stopping
echo ===================================================
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$connections = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue; $stopped = $false; foreach ($connection in $connections) { $processId = $connection.OwningProcess; $process = Get-CimInstance Win32_Process -Filter ('ProcessId = ' + $processId) -ErrorAction SilentlyContinue; if ($process -and $process.CommandLine -match 'uvicorn\s+web\.app:app') { Stop-Process -Id $processId -Force -ErrorAction Stop; Write-Host ('Stopped SeedanceMini v2 server. PID: ' + $processId); $stopped = $true } }; if (-not $connections) { Write-Host 'SeedanceMini v2 is not running on port 8000.'; exit 0 }; if (-not $stopped) { Write-Host 'Port 8000 is used by another program. Nothing was stopped.'; exit 2 }"

if errorlevel 2 (
  echo.
  echo For safety, no unrelated program was stopped.
  pause
  exit /b 2
)

echo.
echo You can close this window now.
pause
exit /b 0
