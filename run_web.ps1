$ErrorActionPreference = "Stop"

$repositoryRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
$webRoot = Join-Path $repositoryRoot "web"

if (-not (Test-Path $python)) {
    throw "The project environment is missing. Run the README setup steps first."
}

$api = Start-Process `
    -FilePath $python `
    -ArgumentList @((Join-Path $repositoryRoot "web_server.py")) `
    -WorkingDirectory $repositoryRoot `
    -WindowStyle Hidden `
    -PassThru

try {
    Start-Sleep -Milliseconds 800
    Start-Process "http://localhost:3000"
    Push-Location $webRoot
    npm.cmd run dev
}
finally {
    Pop-Location
    if ($api -and -not $api.HasExited) {
        Stop-Process -Id $api.Id
    }
}
