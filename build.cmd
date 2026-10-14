@echo off
rem Compiles Meeting Intelligence into one folder: release\MeetingIntelligence\MeetingIntelligence.exe
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build.ps1"
if errorlevel 1 (echo. & echo Build failed. See the messages above. & pause & exit /b 1)
echo.
echo Build finished. Open the release\MeetingIntelligence folder.
pause
