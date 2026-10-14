# Builds Meeting Intelligence into one folder of compiled programs: release\MeetingIntelligence\
# Needs: Python 3.11+ and Node.js 18+ installed. Run through build.cmd.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

function Run($file, $arguments) {
  & $file @arguments
  if ($LASTEXITCODE -ne 0) { throw "Command failed: $file $($arguments -join ' ')" }
}

Write-Host '[1/4] Python build environment'
$py = if (Get-Command py -ErrorAction SilentlyContinue) { @('py','-3') } else { @('python') }
if (-not (Test-Path '.build-venv\Scripts\python.exe')) { Run $py[0] (@($py | Select-Object -Skip 1) + @('-m','venv','.build-venv')) }
$venvPy = Join-Path $root '.build-venv\Scripts\python.exe'
Run $venvPy @('-m','pip','install','--quiet','--upgrade','pip')
Run $venvPy @('-m','pip','install','--quiet','-r','backend\requirements-build.txt')
# Optional PostgreSQL driver: only from a ready-made package (never compiled); skipped when none exists for this Python.
try { & $venvPy -m pip install --quiet --only-binary ':all:' -r backend\requirements-postgres-optional.txt } catch { }
if ($LASTEXITCODE -ne 0) { Write-Host '  (PostgreSQL driver not installed - fine for the local SQLite build)' }

Write-Host '[2/4] Web app'
Push-Location frontend
Run 'npm.cmd' @('install','--no-audit','--no-fund')
$env:VITE_DEMO_MODE = 'true'; $env:VITE_API_BASE = '/api/v1'
Run 'npm.cmd' @('run','build')
Pop-Location

Write-Host '[3/4] Compiling program'
foreach ($d in 'release','build-tmp') { if (Test-Path $d) { Remove-Item $d -Recurse -Force } }
Push-Location backend
$env:WEB_SRC = Join-Path $root 'frontend\dist'
Run $venvPy @('-m','PyInstaller','--noconfirm','--clean','--distpath',(Join-Path $root 'release'),'--workpath',(Join-Path $root 'build-tmp'),'meeting_intelligence.spec')
Pop-Location

Write-Host '[4/4] Finishing'
$out = Join-Path $root 'release\MeetingIntelligence'
Copy-Item '.env.example' (Join-Path $out '.env.example')
@'
@echo off
rem Stops the background Meeting Intelligence program.
taskkill /IM MeetingIntelligence.exe /F >nul 2>&1
if errorlevel 1 (echo Meeting Intelligence was not running.) else (echo Meeting Intelligence stopped.)
timeout /t 3 >nul
'@ | Set-Content (Join-Path $out 'Stop Meeting Intelligence.cmd') -Encoding ASCII
@'
Meeting Intelligence - compiled build
Double-click MeetingIntelligence.exe. No command window is shown; it runs in the background and your browser opens automatically.
Double-click it again at any time to reopen the page.
Sign in as admin / Meeting$1, or use Sign up.
Data and logs are kept in the "docs" folder next to the program (created on first run).
Optional settings: copy .env.example to .env in this folder, edit, and restart.
To stop: run 'Stop Meeting Intelligence.cmd'. Problems, if any, are written to docs\logs\app.log.
'@ | Set-Content (Join-Path $out 'README.txt') -Encoding ASCII
if (Test-Path 'build-tmp') { Remove-Item 'build-tmp' -Recurse -Force }
Write-Host "Done: $out"
