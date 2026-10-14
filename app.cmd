@echo off
setlocal
cd /d "%~dp0"
title Meeting Intelligence Platform
if not exist "backend\app\main.py" goto NO_PROJECT
if not exist "frontend\package.json" goto NO_PROJECT
where node >nul 2>nul
if errorlevel 1 goto NO_NODE
for /f "tokens=1 delims=." %%v in ('node -p "process.versions.node"') do set NODE_MAJOR=%%v
if %NODE_MAJOR% LSS 18 goto OLD_NODE
where py >nul 2>nul
if errorlevel 1 (
  where python >nul 2>nul
  if errorlevel 1 goto NO_PYTHON
)
if not exist "docs\data" mkdir "docs\data"
if not exist "docs\logs" mkdir "docs\logs"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-local.ps1"
if errorlevel 1 (
  echo.
  echo Local startup did not complete. Review the messages above and docs\logs folder.
  pause
  exit /b 1
)
echo Meeting Intelligence Platform is running. Use app-stop.cmd to stop it.
endlocal
exit /b 0

:NO_PROJECT
echo [ERROR] The full pack was not extracted. Run app.cmd from the extracted pack folder.
goto FAIL
:NO_NODE
echo [ERROR] Node.js 18 or later is required. Install it from https://nodejs.org and retry.
goto FAIL
:OLD_NODE
echo [ERROR] Node.js 18 or later is required. Current major version is %NODE_MAJOR%.
goto FAIL
:NO_PYTHON
echo [ERROR] Python 3.11 or later is required. Install Python from https://www.python.org/downloads/windows/ and retry.
goto FAIL
:FAIL
echo.
pause
exit /b 1
