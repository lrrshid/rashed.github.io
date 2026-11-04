<#
.SYNOPSIS
  Run the Capability Portfolio Command automated tests with the project virtual environment.

.DESCRIPTION
  Default: unit + integration suite (pytest.ini already excludes the e2e and oracle markers).
  -E2E:    also runs the real-browser checks (pytest -m e2e; needs Playwright + Microsoft Edge).
  Any extra arguments are passed to pytest (e.g. -k reset, -x).
  Exits with pytest's exit code (the first non-zero one when both runs happen).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\run_tests.ps1
  powershell -ExecutionPolicy Bypass -File scripts\run_tests.ps1 -E2E
  powershell -ExecutionPolicy Bypass -File scripts\run_tests.ps1 -k reset_demo
#>
# A plain script (no [Parameter()] attribute): an advanced script would take pytest options such as -v, -p or -o as
# PowerShell common parameters (-Verbose, -PipelineVariable, ...) instead of passing them on.
param([switch]$E2E)
$PytestArgs = @($args)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "No virtual environment at $venvPython. Run scripts\run_dev.ps1 once (it creates .venv)." -ForegroundColor Red
    exit 4
}
if ($null -eq $PytestArgs) { $PytestArgs = @() }

$results = @()
Push-Location (Join-Path $root "backend")
try {
    Write-Host "== Unit + integration tests ==" -ForegroundColor Cyan
    $start = Get-Date
    & $venvPython -m pytest -p no:cacheprovider -rfEx @PytestArgs
    $results += [pscustomobject]@{ Suite = "unit+integration"; ExitCode = $LASTEXITCODE; Seconds = [int]((Get-Date) - $start).TotalSeconds }

    if ($E2E) {
        Write-Host "== End-to-end browser tests (-m e2e) ==" -ForegroundColor Cyan
        $start = Get-Date
        & $venvPython -m pytest -p no:cacheprovider -rfEx -m e2e @PytestArgs
        $results += [pscustomobject]@{ Suite = "e2e"; ExitCode = $LASTEXITCODE; Seconds = [int]((Get-Date) - $start).TotalSeconds }
    }
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "== Summary ==" -ForegroundColor Cyan
foreach ($r in $results) {
    $status = switch ($r.ExitCode) { 0 { "PASSED" } 1 { "FAILED" } 5 { "NO TESTS COLLECTED" } default { "ERROR (exit $($r.ExitCode))" } }
    $color = if ($r.ExitCode -eq 0) { "Green" } else { "Red" }
    Write-Host ("{0,-18} {1,-22} {2,5}s" -f $r.Suite, $status, $r.Seconds) -ForegroundColor $color
}

$exitCode = 0
foreach ($r in $results) { if ($r.ExitCode -ne 0) { $exitCode = $r.ExitCode; break } }
exit $exitCode
