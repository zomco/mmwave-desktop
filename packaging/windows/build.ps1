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

function Get-BuildConfiguration {
    param([string]$Executable)
    $StartInfo = New-Object System.Diagnostics.ProcessStartInfo
    $StartInfo.FileName = $Executable
    $StartInfo.Arguments = "-buildconf"
    $StartInfo.UseShellExecute = $false
    $StartInfo.CreateNoWindow = $true
    $StartInfo.RedirectStandardOutput = $true
    $StartInfo.RedirectStandardError = $true
    $Process = New-Object System.Diagnostics.Process
    $Process.StartInfo = $StartInfo
    if (-not $Process.Start()) {
        throw "Could not start $Executable -buildconf."
    }
    $Stdout = $Process.StandardOutput.ReadToEnd()
    $Stderr = $Process.StandardError.ReadToEnd()
    $Process.WaitForExit()
    if ($Process.ExitCode -ne 0) {
        throw "$Executable -buildconf failed with exit code $($Process.ExitCode)."
    }
    return $Stdout + "`n" + $Stderr
}

Write-Host "Verifying TraceCue source, contracts, and distributable frontend..."
if (-not (Test-Path -LiteralPath $BuildPython -PathType Leaf)) {
    Invoke-Checked "python" @("-m", "venv", "--system-site-packages", $BuildVenv)
}
Invoke-Checked $BuildPython @("-m", "pip", "install", "--requirement", "requirements-dev.lock.txt")
Invoke-Checked $BuildPython @("-m", "pip", "install", "--no-build-isolation", "--no-deps", "-e", "engine", "-e", "integrations/hikvision", "-e", "gateway", "-e", "desktop/backend")
Invoke-Checked $BuildPython @("scripts/ci/verify_repo.py", "--security")
$PytestTempRoot = Join-Path $RepositoryRoot ("build\pytest-" + [guid]::NewGuid().ToString("N"))
try {
    # pytest's default %TEMP% base may be owned by another Windows identity (for
    # example an IDE sandbox or an elevated shell). A unique repository-local
    # base keeps verification independent from that global ACL state.
    Invoke-Checked $BuildPython @(
        "-m", "pytest",
        "engine/tests", "integrations/hikvision/tests", "gateway/tests", "desktop/backend/tests",
        "--basetemp", $PytestTempRoot,
        "-q"
    )
} finally {
    $ResolvedBuildRoot = [System.IO.Path]::GetFullPath((Join-Path $RepositoryRoot "build"))
    $ResolvedPytestTemp = [System.IO.Path]::GetFullPath($PytestTempRoot)
    if (-not $ResolvedPytestTemp.StartsWith($ResolvedBuildRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Unsafe pytest cleanup target: $ResolvedPytestTemp"
    }
    if (Test-Path -LiteralPath $ResolvedPytestTemp) {
        Remove-Item -LiteralPath $ResolvedPytestTemp -Recurse -Force
    }
}
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
    $Blockers = ($Manifest.release_blockers -join "; ")
    throw "Release is blocked: release/manifest.json has release_ready=false. Remaining blockers: $Blockers"
}
if (-not $env:TRACECUE_SIGNING_THUMBPRINT) {
    throw "Release is blocked: TRACECUE_SIGNING_THUMBPRINT is not configured."
}
Invoke-Checked $BuildPython @("-m", "pip", "install", "--requirement", "packaging/windows/requirements.lock.txt")

$FFmpegPath = Join-Path $RepositoryRoot "packaging\windows\tools\ffmpeg.exe"
$FFprobePath = Join-Path $RepositoryRoot "packaging\windows\tools\ffprobe.exe"
$GPLLicensePath = Join-Path $RepositoryRoot "packaging\windows\tools\COPYING.GPLv3"
$LGPLLicensePath = Join-Path $RepositoryRoot "packaging\windows\tools\COPYING.LGPLv3"
foreach ($Tool in @($FFmpegPath, $FFprobePath, $GPLLicensePath, $LGPLLicensePath)) {
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
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $GPLLicensePath).Hash.ToLowerInvariant() -ne $Manifest.ffmpeg_gpl_license_sha256) {
    throw "COPYING.GPLv3 hash does not match release/manifest.json"
}
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $LGPLLicensePath).Hash.ToLowerInvariant() -ne $Manifest.ffmpeg_lgpl_license_sha256) {
    throw "COPYING.LGPLv3 hash does not match release/manifest.json"
}
$FFmpegVersion = (& $FFmpegPath -version | Select-Object -First 1)
if ($FFmpegVersion -notlike "ffmpeg version $($Manifest.ffmpeg_version)*") {
    throw "ffmpeg.exe version does not match release/manifest.json"
}
$BuildConf = Get-BuildConfiguration $FFmpegPath
foreach ($Forbidden in @("--enable-gpl", "--enable-nonfree", "--enable-libx264", "--enable-libx265")) {
    if ($BuildConf.Contains($Forbidden)) {
        throw "FFmpeg build contains forbidden configuration: $Forbidden"
    }
}
if (-not $BuildConf.Contains("--enable-version3") -or -not $BuildConf.Contains("--enable-libopenh264")) {
    throw "FFmpeg build is missing the pinned LGPLv3/OpenH264 configuration."
}
$FFmpegSourcePath = Join-Path $RepositoryRoot "release\output\source\ffmpeg-$($Manifest.ffmpeg_source_commit).tar.gz"
$FFmpegBuildSourcePath = Join-Path $RepositoryRoot "release\output\source\ffmpeg-builds-$($Manifest.ffmpeg_build_source_commit).tar.gz"
$SourceInputs = @(
    [pscustomobject]@{ Path = $FFmpegSourcePath; Sha256 = $Manifest.ffmpeg_source_sha256 },
    [pscustomobject]@{ Path = $FFmpegBuildSourcePath; Sha256 = $Manifest.ffmpeg_build_source_sha256 }
)
foreach ($SourceInput in $SourceInputs) {
    if (-not (Test-Path -LiteralPath $SourceInput.Path -PathType Leaf)) {
        throw "Pinned FFmpeg source input is missing: $($SourceInput.Path). Run packaging/windows/fetch-ffmpeg.ps1 -IncludeSourceSnapshots."
    }
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $SourceInput.Path).Hash.ToLowerInvariant() -ne $SourceInput.Sha256) {
        throw "Pinned FFmpeg source hash does not match release/manifest.json: $($SourceInput.Path)"
    }
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
Copy-Item -LiteralPath $FFmpegSourcePath,$FFmpegBuildSourcePath -Destination (Join-Path $RepositoryRoot "artifacts") -Force
Get-ChildItem -LiteralPath (Join-Path $RepositoryRoot "artifacts") -File | ForEach-Object {
    $Hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant()
    "$Hash  $($_.Name)"
} | Set-Content -Encoding utf8 (Join-Path $RepositoryRoot "artifacts\checksums.sha256")
Write-Host "TraceCue signed release artifacts are ready under artifacts/."
