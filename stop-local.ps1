# Stops everything started by app.cmd, including child processes, so the folder can be moved or deleted.
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$pidFile = Join-Path $root 'docs\data\local-processes.json'

# 1. Stop the saved processes together with all of their child processes.
if (Test-Path $pidFile) {
    try {
        $saved = Get-Content $pidFile -Raw | ConvertFrom-Json
        foreach ($name in @('frontend','worker','api')) {
            $id = [int]$saved.$name
            if ($id -gt 0 -and (Get-Process -Id $id -ErrorAction SilentlyContinue)) {
                & taskkill.exe /PID $id /T /F *> $null
                Write-Host "Stopped $name (process $id)."
            }
        }
    } catch { Write-Host 'Could not read the saved process list; scanning for leftovers instead.' }
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
} else {
    Write-Host 'No saved process list found; scanning for leftovers.'
}

# 2. Sweep any leftover python/node/esbuild process that still runs from this folder.
$names = @('python.exe','pythonw.exe','node.exe','esbuild.exe')
$left = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $_.ProcessId -ne $PID -and $names -contains $_.Name -and
    (($_.ExecutablePath -and $_.ExecutablePath.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)) -or
     ($_.CommandLine -and $_.CommandLine.IndexOf($root, [StringComparison]::OrdinalIgnoreCase) -ge 0))
})
foreach ($p in $left) {
    & taskkill.exe /PID $p.ProcessId /T /F *> $null
    Write-Host "Stopped leftover $($p.Name) (process $($p.ProcessId))."
}
Start-Sleep -Milliseconds 500
Write-Host 'Meeting Intelligence is stopped. You can now close this window and move or delete the folder.'
