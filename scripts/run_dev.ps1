<#
.SYNOPSIS
  Set up (first run) and start Capability Portfolio Command locally.

.DESCRIPTION
  - Creates .venv and installs the pinned dependencies if needed. On the air-gapped network they are installed from
    the local wheelhouse\ folder (built once on a connected machine with scripts\build_wheelhouse.ps1); nothing is
    downloaded.
  - Requires a .env file (copy .env.example).
  - Starts the app at http://127.0.0.1:8770 using waitress.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\run_dev.ps1
  powershell -ExecutionPolicy Bypass -File scripts\run_dev.ps1 -Port 5000
#>
param(
    [int]$Port = 8770,
    [string]$BindHost = "127.0.0.1"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$venvPython = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    $python = (Get-Command python -ErrorAction SilentlyContinue)
    $candidate = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
    if (Test-Path $candidate) { $pythonExe = $candidate }
    elseif ($python -and $python.Source -notlike "*WindowsApps*") { $pythonExe = $python.Source }
    else { throw "Python 3.12 not found. Install it with the Python 3.12 installer copied with the wheelhouse, then retry." }
    Write-Host "Creating virtual environment..."
    & $pythonExe -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Creating the virtual environment failed." }
}

# (Re)install the pinned dependencies when the venv is new or a requirements or constraints file changed since the
# last successful install. A failed install is an error (and is retried next run).
$reqHash = (Get-ChildItem (Join-Path $root "backend\*.txt") |
    Where-Object { $_.Name -like "requirements*" -or $_.Name -eq "constraints.txt" } | Sort-Object Name |
    Get-FileHash -Algorithm SHA256 | ForEach-Object { $_.Hash }) -join ""
$stamp = Join-Path $root ".venv\requirements.sha256"
$installed = if (Test-Path $stamp) { (Get-Content $stamp -Raw).Trim() } else { "" }
if ($installed -ne $reqHash) {
    $wheelhouse = Join-Path $root "wheelhouse"
    if (Test-Path $wheelhouse) {
        # Air-gapped: only the local wheelhouse folder, never the internet.
        Write-Host "Installing dependencies from $wheelhouse (offline)..."
        & $venvPython -m pip install --no-index --find-links $wheelhouse -r backend\requirements-dev.txt --quiet
        $hint = "A package is missing from wheelhouse\: rebuild it with scripts\build_wheelhouse.ps1 on a connected machine."
    } else {
        Write-Host "Installing dependencies (no wheelhouse\ folder: using the package index)..."
        & $venvPython -m pip install -r backend\requirements-dev.txt --quiet
        $hint = "On the air-gapped network copy a wheelhouse\ folder (scripts\build_wheelhouse.ps1) next to this project."
    }
    if ($LASTEXITCODE -ne 0) {
        Remove-Item $stamp -ErrorAction SilentlyContinue
        throw "Installing the dependencies failed. $hint"
    }
    Set-Content -Path $stamp -Value $reqHash -Encoding ascii
}

if (-not (Test-Path (Join-Path $root ".env"))) {
    throw "No .env file. Copy .env.example to .env (the demo needs no accounts in it; it uses the mock accounts)."
}

Set-Location (Join-Path $root "backend")
Write-Host "Capability Portfolio Command: http://${BindHost}:${Port}  (Ctrl+C to stop)"
& $venvPython -m waitress --listen="${BindHost}:${Port}" --ident= wsgi:app  # --ident=: no "Server: waitress" header
