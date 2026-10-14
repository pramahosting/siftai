$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
$logDir = Join-Path $root 'docs\logs'
$dataDir = Join-Path $root 'docs\data'
New-Item -ItemType Directory -Force -Path $logDir,$dataDir | Out-Null

# Upgrade from older versions: move the former root-level data and logs folders into docs.
foreach ($pair in @(@('data',$dataDir),@('logs',$logDir))) {
    $old = Join-Path $root $pair[0]
    if ((Test-Path $old) -and ((Resolve-Path $old).Path -ne (Resolve-Path $pair[1]).Path)) {
        Get-ChildItem -LiteralPath $old -Force | ForEach-Object {
            $target = Join-Path $pair[1] $_.Name
            if (-not (Test-Path $target)) { Move-Item -LiteralPath $_.FullName -Destination $target -Force -ErrorAction SilentlyContinue }
        }
        if (-not (Get-ChildItem -LiteralPath $old -Force)) { Remove-Item -LiteralPath $old -Force -ErrorAction SilentlyContinue }
    }
}

$pythonLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
if ($pythonLauncher) {
    $versionText = & $pythonLauncher.Source -3 --version 2>&1 | Out-String
    if ($versionText -notmatch 'Python 3\.(1[1-9]|[2-9][0-9])') { throw "Python 3.11 or later is required. Found: $versionText" }
    $basePython = $pythonLauncher.Source
    $baseArgs = @('-3')
} else {
    $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    if (-not $pythonCommand) { throw 'Python 3.11 or later is required. Install it from https://www.python.org/downloads/windows/.' }
    $versionText = & $pythonCommand.Source --version 2>&1 | Out-String
    if ($versionText -notmatch 'Python 3\.(1[1-9]|[2-9][0-9])') { throw "Python 3.11 or later is required. Found: $versionText" }
    $basePython = $pythonCommand.Source
    $baseArgs = @()
}

$venvPython = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPython)) {
    Write-Host '[SETUP] Creating the private Python environment...'
    & $basePython @baseArgs -m venv (Join-Path $root '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
}
$requirements = Join-Path $root 'backend\requirements-local.txt'
$requirementsHash = (Get-FileHash -Algorithm SHA256 $requirements).Hash
$stamp = Join-Path $root '.venv\requirements.sha256'
if (-not (Test-Path $stamp) -or (Get-Content $stamp -Raw).Trim() -ne $requirementsHash) {
    Write-Host '[SETUP] Installing backend packages...'
    & $venvPython -m pip install --disable-pip-version-check -r $requirements
    if ($LASTEXITCODE -ne 0) { throw 'Backend package installation failed. Check internet access and logs.' }
    Set-Content -Path $stamp -Value $requirementsHash -Encoding ASCII
}

$node = (Get-Command node.exe -ErrorAction Stop).Source
$npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $npm) { throw 'npm was not found. Repair the Node.js installation and retry.' }
if (-not (Test-Path (Join-Path $root 'frontend\node_modules\vite\bin\vite.js'))) {
    Write-Host '[SETUP] Installing the frontend packages on first launch...'
    Push-Location (Join-Path $root 'frontend')
    try { & $npm.Source install --no-audit --no-fund; if ($LASTEXITCODE -ne 0) { throw 'Frontend package installation failed.' } }
    finally { Pop-Location }
}

# Local evaluation is self-contained and uses a persistent SQLite file. Production
# and Docker deployments continue to use the PostgreSQL/Neon DATABASE_URL setting.
$env:APP_ENV = 'development'
$env:AUTH_MODE = 'local'
$env:ALLOW_LOCAL_AUTH = 'true'
$env:DATABASE_URL = 'sqlite+aiosqlite:///./docs/data/meeting_intelligence.db'
$env:FRONTEND_ORIGIN = 'http://localhost:5173'
$env:PYTHONPATH = Join-Path $root 'backend'
$env:AUDIO_STORAGE_DIR = Join-Path $dataDir 'audio'
$env:VITE_DEMO_MODE = 'true'
New-Item -ItemType Directory -Force -Path $env:AUDIO_STORAGE_DIR | Out-Null

Write-Host '[SETUP] Preparing the local database...'
& $venvPython -m alembic -c (Join-Path $root 'backend\alembic.ini') upgrade head
if ($LASTEXITCODE -ne 0) { throw 'Local database setup failed.' }

Write-Host '[SETUP] Loading sample data and picking up the calendar on this computer...'
Push-Location $root
& $venvPython -m app.startup
Pop-Location
if ($LASTEXITCODE -ne 0) { Write-Host '  (Startup data step reported a problem; the app will still start. See docs/logs.)' }

$pidFile = Join-Path $dataDir 'local-processes.json'
if (Test-Path $pidFile) {
    try {
        $old = Get-Content $pidFile -Raw | ConvertFrom-Json
        foreach ($id in @($old.api,$old.worker,$old.frontend)) {
            if ($id -and (Get-Process -Id ([int]$id) -ErrorAction SilentlyContinue)) { Stop-Process -Id ([int]$id) -Force -ErrorAction SilentlyContinue }
        }
    } catch { }
}

$apiArgs = @('-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000')
$apiProc = Start-Process -FilePath $venvPython -ArgumentList $apiArgs -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDir 'backend.log') -RedirectStandardError (Join-Path $logDir 'backend-error.log')
$workerArgs = @('-m','app.workers.runner')
$workerProc = Start-Process -FilePath $venvPython -ArgumentList $workerArgs -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDir 'worker.log') -RedirectStandardError (Join-Path $logDir 'worker-error.log')
$env:VITE_DEMO_MODE = 'true'
$vite = Join-Path $root 'frontend\node_modules\vite\bin\vite.js'
$frontArgs = '"' + $vite + '" --host 127.0.0.1 --port 5173 --strictPort'
$frontProc = Start-Process -FilePath $node -ArgumentList $frontArgs -WorkingDirectory (Join-Path $root 'frontend') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDir 'frontend.log') -RedirectStandardError (Join-Path $logDir 'frontend-error.log')
@{ api=$apiProc.Id; worker=$workerProc.Id; frontend=$frontProc.Id } | ConvertTo-Json | Set-Content -Encoding UTF8 $pidFile

Write-Host '[START] Starting the API, job worker, and frontend...'
$deadline = (Get-Date).AddMinutes(4)
$ready = $false
while ((Get-Date) -lt $deadline) {
    if (-not (Get-Process -Id $apiProc.Id -ErrorAction SilentlyContinue)) { throw 'The API stopped during startup. See docs/logs/backend-error.log.' }
    if (-not (Get-Process -Id $workerProc.Id -ErrorAction SilentlyContinue)) { throw 'The job worker stopped during startup. See docs/logs/worker-error.log.' }
    if (-not (Get-Process -Id $frontProc.Id -ErrorAction SilentlyContinue)) { throw 'The frontend stopped during startup. See docs/logs/frontend-error.log.' }
    try {
        $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/v1/health' -TimeoutSec 2
        $page = Invoke-WebRequest -Uri 'http://127.0.0.1:5173' -TimeoutSec 2 -UseBasicParsing
        if ($health.status -eq 'ok' -and $health.database -eq 'ok' -and $page.StatusCode -eq 200) { $ready = $true; break }
    } catch { }
    Start-Sleep -Seconds 2
}
if (-not $ready) { throw 'The API, database, worker, and frontend did not all become ready in four minutes. Review the docs\logs folder.' }
Write-Host '[READY] API, SQLite database, worker, and frontend are ready. Opening the browser...'
Start-Process -FilePath 'http://localhost:5173/'

