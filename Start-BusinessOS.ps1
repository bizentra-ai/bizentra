$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$backendPath = Join-Path $projectRoot 'backend'
$frontendPath = Join-Path $projectRoot 'frontend'
$pythonPath = Join-Path $backendPath '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Run the setup steps in README.md first.' }
if (-not (Test-Path -LiteralPath (Join-Path $frontendPath 'dist\index.html'))) { throw 'Build the frontend using the README instructions first.' }
try {
    $existing = Invoke-RestMethod 'http://127.0.0.1:5173/api/health' -TimeoutSec 2
    if ($existing.status -eq 'ok') { Write-Host 'BusinessOS is already running: http://127.0.0.1:5173'; return }
} catch { }
Push-Location $backendPath
try {
    & $pythonPath -m app.config_check
    if ($LASTEXITCODE -ne 0) { throw 'Backend configuration validation failed.' }
    & $pythonPath -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'Database migration failed.' }
} finally { Pop-Location }
$apiProcess = Start-Process -FilePath $pythonPath -ArgumentList @('-m','uvicorn','app.main:app','--host','0.0.0.0','--port','8000') -WorkingDirectory $backendPath -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $backendPath 'server.log') -RedirectStandardError (Join-Path $backendPath 'server-error.log')
$nodePath = (Get-Command node.exe -ErrorAction Stop).Source
$uiProcess = Start-Process -FilePath $nodePath -ArgumentList @('node_modules/vite/bin/vite.js','preview','--host','0.0.0.0','--port','5173','--strictPort','--configLoader','runner') -WorkingDirectory $frontendPath -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $frontendPath 'server.log') -RedirectStandardError (Join-Path $frontendPath 'server-error.log')
@{ api = $apiProcess.Id; ui = $uiProcess.Id } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $projectRoot '.local-processes.json')
for ($attempt=0; $attempt -lt 15; $attempt++) {
    Start-Sleep -Milliseconds 500
    try { if ((Invoke-RestMethod 'http://127.0.0.1:5173/api/health' -TimeoutSec 2).status -eq 'ok') { Write-Host 'BusinessOS is ready: http://127.0.0.1:5173'; return } } catch { }
}
throw 'BusinessOS did not start. Review backend/server-error.log and frontend/server-error.log.'
