<#
.SYNOPSIS
  Build the offline bundle for the company VM: dist\cpc-<version>.tar.gz (one file to carry into the network).

.DESCRIPTION
  Runs on the internet-connected Windows PC with Docker Desktop (Linux containers) running:
    1. the tests (scripts\run_tests.ps1), unless -SkipTests
    2. docker build of the app image cpc:<version> (predeployment\Dockerfile)
    3. a test start of that image on http://127.0.0.1:18080 (empty SQLite in /tmp, read-only filesystem): health,
       the page and a script must answer
    4. docker pull nginx:1.27.3-alpine
    5. dist\cpc-<version>\: deployment files, Oracle scripts, docs, VERSION, both images (docker save),
       LF line endings, SHA256SUMS; no secret file can get in
    6. dist\cpc-<version>.tar.gz and its SHA-256 (note it, to check the copy on the VM)
  The version is yyyy.MM.dd-<commit>; uncommitted work adds -dirty.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File predeployment\build.ps1
  powershell -ExecutionPolicy Bypass -File predeployment\build.ps1 -SkipTests            # the tests just passed
  powershell -ExecutionPolicy Bypass -File predeployment\build.ps1 -Platform linux/arm64 # an ARM (aarch64) VM
#>
param(
    [switch]$SkipTests,
    [ValidateSet("linux/amd64", "linux/arm64")][string]$Platform = "linux/amd64"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$Nginx = "nginx:1.27.3-alpine"
$SmokePort = 18080

function Step($text) { Write-Host ""; Write-Host "== $text" -ForegroundColor Cyan }
function Native($what) { if ($LASTEXITCODE -ne 0) { throw "$what failed (exit code $LASTEXITCODE)." } }

# ---------------------------------------------------------------- prerequisites and version
Step "Checking Docker and Git"
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "Docker is not installed. Install Docker Desktop (Linux containers)." }
docker info --format "{{.OSType}}" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Docker is not running. Start Docker Desktop and wait until it says 'Engine running'." }
$commit = (git rev-parse --short HEAD).Trim(); Native "git rev-parse"
$dirty = [bool](git status --porcelain)
$version = (Get-Date -Format "yyyy.MM.dd") + "-" + $commit + $(if ($dirty) { "-dirty" } else { "" })
$image = "cpc:$version"
Write-Host "Version $version  ($Platform)"
if ($dirty) { Write-Host "Uncommitted changes: the version is marked -dirty. Commit first for a bundle you can trace." -ForegroundColor Yellow }

# ---------------------------------------------------------------- 1. tests
if (-not $SkipTests) {
    Step "1. Tests"
    & powershell -ExecutionPolicy Bypass -File (Join-Path $root "scripts\run_tests.ps1")
    if ($LASTEXITCODE -ne 0) { throw "The tests failed: no bundle is built." }
} else { Step "1. Tests skipped (-SkipTests)" }

# ---------------------------------------------------------------- 2. image
Step "2. docker build $image"
docker build --pull --platform $Platform -f predeployment/Dockerfile -t $image --label "org.opencontainers.image.version=$version" `
    --label "org.opencontainers.image.revision=$commit" .
Native "docker build"

# ---------------------------------------------------------------- 3. test start
Step "3. Test start on http://127.0.0.1:$SmokePort"
$smoke = "cpc-smoke-$PID"
cmd /c "docker rm -f $smoke >nul 2>&1"   # 2>$null on a native command throws in PowerShell 5.1
# A throwaway SETTINGS_KEY, as install.sh writes one into app.env on the VM: the read-only container cannot create
# the key file the local demo uses (data/settings.key), and /app/data is not mounted in this test.
$keyBytes = New-Object byte[] 32
[System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($keyBytes)
$smokeKey = [Convert]::ToBase64String($keyBytes)
docker run -d --name $smoke --platform $Platform -p "127.0.0.1:${SmokePort}:8080" --read-only --tmpfs /tmp --cap-drop ALL `
    -e APP_PROFILE=demo -e APP_ENV=production -e DEMO_DB_PATH=/tmp/smoke.db -e SESSION_COOKIE_SECURE=false `
    -e "SETTINGS_KEY=$smokeKey" $image | Out-Null
Native "docker run"
try {
    $base = "http://127.0.0.1:$SmokePort"
    $up = $false
    for ($i = 0; $i -lt 60 -and -not $up; $i++) {
        Start-Sleep -Seconds 2
        try { $up = (Invoke-WebRequest "$base/api/v1/health" -UseBasicParsing -TimeoutSec 5).Content -match '"UP"' } catch { }
    }
    if (-not $up) { docker logs --tail 60 $smoke; throw "The image did not become healthy within 2 minutes (its log is above)." }
    $page = Invoke-WebRequest "$base/" -UseBasicParsing -TimeoutSec 10
    if ($page.Content -notmatch '/js/main\.js') { throw "The home page did not come back from the image." }
    $script = Invoke-WebRequest "$base/js/main.js" -UseBasicParsing -TimeoutSec 10
    if ($script.Headers["Content-Type"] -notmatch 'javascript') { throw "main.js is not served as JavaScript: $($script.Headers['Content-Type'])" }
    if ($page.Headers["Content-Security-Policy"] -notmatch "default-src 'self'") { throw "The security headers are missing." }
    Write-Host "Health UP, page, script and security headers OK"
} finally {
    cmd /c "docker rm -f $smoke >nul 2>&1"   # 2>$null on a native command throws in PowerShell 5.1
}

# ---------------------------------------------------------------- 4. nginx
Step "4. docker pull $Nginx"
docker pull --platform $Platform $Nginx
Native "docker pull"

# ---------------------------------------------------------------- 5. the bundle folder
Step "5. Assembling dist\cpc-$version"
$dist = Join-Path $root "dist"
$name = "cpc-$version"
$stage = Join-Path $dist $name
if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
New-Item -ItemType Directory -Force $stage | Out-Null

# deployment\ minus anything made on a VM (settings, data, certificates, backups)
$skip = '^(app\.env|ldap\.env|\.env|install\.conf|data|backups)$'
Get-ChildItem (Join-Path $root "deployment") -Force | Where-Object { $_.Name -notmatch $skip } |
    ForEach-Object { Copy-Item $_.FullName -Destination $stage -Recurse -Force }
Get-ChildItem (Join-Path $stage "certs"), (Join-Path $stage "ldap") -File -Force |
    Where-Object { $_.Name -ne "README.md" } | Remove-Item -Force
Copy-Item (Join-Path $root "ldap.env.example") $stage
New-Item -ItemType Directory -Force (Join-Path $stage "oracle-scripts"), (Join-Path $stage "docs"), (Join-Path $stage "images") | Out-Null
Copy-Item (Join-Path $root "db\oracle\V*.sql") (Join-Path $stage "oracle-scripts")
Copy-Item (Join-Path $root "db\oracle\runtime-grants.sql") (Join-Path $stage "oracle-scripts")
foreach ($doc in "docs\oracle-migration.md", "docs\SETTINGS.md", "docs\IT_REQUEST.md", "docs\LDAP_IT_MANUAL.md", "docs\LDAP_SETUP.txt") {
    Copy-Item (Join-Path $root $doc) (Join-Path $stage "docs")
}

# Text files: UTF-8 without BOM, LF line endings (bash and sha256sum on the VM).
$utf8 = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText((Join-Path $stage "VERSION"), "$version`n", $utf8)
# install.sh refuses a kit built for another CPU type than the VM's.
[System.IO.File]::WriteAllText((Join-Path $stage "IMAGE_PLATFORM"), "$Platform`n", $utf8)
Get-ChildItem $stage -Recurse -File | Where-Object { $_.Extension -in ".sh", ".yml", ".conf", ".md", ".example", ".sql", ".txt", ".template" } |
    ForEach-Object {
        $text = [System.IO.File]::ReadAllText($_.FullName).Replace("`r`n", "`n")
        [System.IO.File]::WriteAllText($_.FullName, $text, $utf8)
    }

# No secret may travel: refuse the build if one slipped in.
$secrets = Get-ChildItem $stage -Recurse -File -Force |
    Where-Object { $_.Name -match '^(\.env|app\.env|ldap\.env|oracle-local\.env)$' -or $_.Extension -in ".key", ".pem", ".crt", ".cer", ".p12", ".pfx" }
if ($secrets) { throw "Refusing to build: secret files in the bundle: $($secrets.FullName -join ', ')" }

Write-Host "docker save $image"
docker save -o (Join-Path $stage "images\$name.tar") $image; Native "docker save (app)"
Write-Host "docker save $Nginx"
docker save -o (Join-Path $stage "images\nginx-1.27.3-alpine.tar") $Nginx; Native "docker save (nginx)"

$lines = Get-ChildItem $stage -Recurse -File | Sort-Object FullName | ForEach-Object {
    $rel = $_.FullName.Substring($stage.Length + 1).Replace("\", "/")
    "{0}  {1}" -f (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower(), $rel
}
[System.IO.File]::WriteAllText((Join-Path $stage "SHA256SUMS"), (($lines -join "`n") + "`n"), $utf8)

# ---------------------------------------------------------------- 6. the one file
Step "6. dist\$name.tar.gz"
$archive = Join-Path $dist "$name.tar.gz"
if (Test-Path $archive) { Remove-Item -Force $archive }
# Python's tarfile (predeployment\pack.py), not Windows tar: the archive carries Linux permissions (install.sh and
# scripts\*.sh executable), so ./install.sh runs straight after tar -xzf on the VM.
& (Join-Path $root ".venv\Scripts\python.exe") (Join-Path $root "predeployment\pack.py") $stage $archive
Native "pack"
$hash = (Get-FileHash $archive -Algorithm SHA256).Hash.ToLower()
$mb = [math]::Round((Get-Item $archive).Length / 1MB, 1)
Write-Host ""
Write-Host "Bundle:  $archive  ($mb MB)" -ForegroundColor Green
Write-Host "SHA-256: $hash"
Write-Host "Note the SHA-256: on the VM, sha256sum cpc-$version.tar.gz must print the same value."
Write-Host "Next: carry the file to the VM, then: tar -xzf $name.tar.gz && cd $name && sudo ./install.sh"
Write-Host "(README.md and README-AR.md inside the kit explain each step)."
