@echo off
setlocal
set "APPDIR=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%APPDIR%stop-local.ps1"
rem Leave the folder so this window does not keep it locked.
cd /d "%TEMP%"
endlocal
pause
