<#
.SYNOPSIS
  Run ONCE on a machine with internet access: downloads every Python package the system needs (pinned versions,
  Windows 64-bit, Python 3.12) into wheelhouse\. Copy the project folder, including wheelhouse\, and the Python 3.12
  installer to the air-gapped network; scripts\run_dev.ps1 then installs offline from wheelhouse\.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\build_wheelhouse.ps1
  powershell -ExecutionPolicy Bypass -File scripts\build_wheelhouse.ps1 -Production   # runtime packages only (no test tools)
#>
param([switch]$Production)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
if (-not (Test-Path $python)) { $python = (Get-Command python).Source }
$wheelhouse = Join-Path $root "wheelhouse"
New-Item -ItemType Directory -Force $wheelhouse | Out-Null
$requirements = if ($Production) { "backend\requirements.txt" } else { "backend\requirements-dev.txt" }

Set-Location $root
& $python -m pip download --dest $wheelhouse --only-binary=:all: --platform win_amd64 --python-version 3.12 `
    --implementation cp -r $requirements
if ($LASTEXITCODE -ne 0) { throw "Downloading the packages failed." }
& $python -m pip download --dest $wheelhouse --only-binary=:all: --platform win_amd64 --python-version 3.12 `
    --implementation cp pip setuptools
Write-Host "Done: $wheelhouse. Copy the whole project folder (with wheelhouse\) and the Python 3.12 installer."
Write-Host "Browser tests use the Microsoft Edge already installed on Windows (no browser download is needed)."
