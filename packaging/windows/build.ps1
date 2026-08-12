param(
    [ValidateSet("Verify", "Release")]
    [string]$Mode = "Verify"
)

$ErrorActionPreference = "Stop"
$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $RepositoryRoot
$BuildVenv = Join-Path $RepositoryRoot "build\verify-venv"
$BuildPython = Join-Path $BuildVenv "Scripts\python.exe"

function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Executable failed with exit code $LASTEXITCODE"
    }
}

Write-Host "Verifying TraceCue source, contracts, and distributable frontend..."
if (-not (Test-Path -LiteralPath $BuildPython -PathType Leaf)) {
    Invoke-Checked "python" @("-m", "venv", "--system-site-packages", $BuildVenv)
}
Invoke-Checked $BuildPython @("-m", "pip", "install", "--requirement", "requirements-dev.lock.txt")
Invoke-Checked $BuildPython @("-m", "pip", "install", "--no-build-isolation", "--no-deps", "-e", "engine", "-e", "integrations/hikvision", "-e", "gateway", "-e", "desktop/backend")
Invoke-Checked $BuildPython @("scripts/ci/verify_repo.py", "--security")
Invoke-Checked $BuildPython @("-m", "pytest", "engine/tests", "integrations/hikvision/tests", "gateway/tests", "desktop/backend/tests", "-q")
Invoke-Checked "npm" @("ci", "--prefix", "desktop/frontend", "--cache", "desktop/frontend/.npm-cache")
Invoke-Checked "npm" @("test", "--prefix", "desktop/frontend")
Invoke-Checked "npm" @("run", "build", "--prefix", "desktop/frontend")

if ($Mode -eq "Verify") {
    Write-Host "TraceCue Windows package source verification passed."
    exit 0
}

$ManifestPath = Join-Path $RepositoryRoot "release\manifest.json"
$Manifest = Get-Content -Raw $ManifestPath | ConvertFrom-Json
if (-not $Manifest.release_ready) {
    throw "Release is blocked: release/manifest.json has release_ready=false. Resolve ADR-0004, pin an LGPL FFmpeg build, and record signing approval."
}
if (-not $env:TRACECUE_SIGNING_THUMBPRINT) {
    throw "Release is blocked: TRACECUE_SIGNING_THUMBPRINT is not configured."
}
Invoke-Checked $BuildPython @("-m", "pip", "install", "--requirement", "packaging/windows/requirements.lock.txt")

$FFmpegPath = Join-Path $RepositoryRoot "packaging\windows\tools\ffmpeg.exe"
$FFprobePath = Join-Path $RepositoryRoot "packaging\windows\tools\ffprobe.exe"
foreach ($Tool in @($FFmpegPath, $FFprobePath)) {
    if (-not (Test-Path -LiteralPath $Tool -PathType Leaf)) {
        throw "Pinned FFmpeg tool is missing: $Tool"
    }
}
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $FFmpegPath).Hash.ToLowerInvariant() -ne $Manifest.ffmpeg_sha256) {
    throw "ffmpeg.exe hash does not match release/manifest.json"
}
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $FFprobePath).Hash.ToLowerInvariant() -ne $Manifest.ffprobe_sha256) {
    throw "ffprobe.exe hash does not match release/manifest.json"
}

Invoke-Checked $BuildPython @("-m", "PyInstaller", "packaging/windows/tracecue.spec", "--noconfirm", "--clean", "--distpath", "artifacts/package", "--workpath", "build/pyinstaller")
$ApplicationExe = Join-Path $RepositoryRoot "artifacts\package\TraceCue\TraceCue.exe"
if (-not (Test-Path -LiteralPath $ApplicationExe -PathType Leaf)) {
    throw "PyInstaller did not produce the expected one-folder application."
}

$SignTool = (Get-Command "signtool.exe" -ErrorAction Stop).Source
Invoke-Checked $SignTool @("sign", "/fd", "SHA256", "/sha1", $env:TRACECUE_SIGNING_THUMBPRINT, "/tr", "http://timestamp.digicert.com", "/td", "SHA256", $ApplicationExe)

$InnoCompiler = (Get-Command "ISCC.exe" -ErrorAction Stop).Source
Invoke-Checked $InnoCompiler @("/DTraceCueVersion=$($Manifest.version)", "packaging/windows/TraceCue.iss")
$InstallerPath = Join-Path $RepositoryRoot "artifacts\TraceCue-$($Manifest.version)-win-x64.exe"
Invoke-Checked $SignTool @("sign", "/fd", "SHA256", "/sha1", $env:TRACECUE_SIGNING_THUMBPRINT, "/tr", "http://timestamp.digicert.com", "/td", "SHA256", $InstallerPath)

Invoke-Checked $BuildPython @("scripts/release/generate_sbom.py", "--output", "artifacts/sbom.cdx.json")
Get-ChildItem -LiteralPath (Join-Path $RepositoryRoot "artifacts") -File | ForEach-Object {
    $Hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant()
    "$Hash  $($_.Name)"
} | Set-Content -Encoding utf8 (Join-Path $RepositoryRoot "artifacts\checksums.sha256")
Write-Host "TraceCue signed release artifacts are ready under artifacts/."
