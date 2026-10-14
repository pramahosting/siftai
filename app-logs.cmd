@echo off
setlocal
cd /d "%~dp0"
if not exist docs\logs\backend.log (
  echo No local logs yet. Start the app with app.cmd first.
  pause
  exit /b 0
)
powershell.exe -NoProfile -Command "Get-Content -Path 'docs\logs\backend.log','docs\logs\backend-error.log','docs\logs\worker.log','docs\logs\worker-error.log','docs\logs\frontend.log','docs\logs\frontend-error.log' -Wait -ErrorAction SilentlyContinue"
endlocal
