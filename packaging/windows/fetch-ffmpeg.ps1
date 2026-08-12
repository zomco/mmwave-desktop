param(
    [string]$ArchivePath = "",
    [switch]$IncludeSourceSnapshots
)

$ErrorActionPreference = "Stop"
$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Manifest = Get-Content -Raw -Encoding utf8 (Join-Path $RepositoryRoot "release\manifest.json") | ConvertFrom-Json
$CacheRoot = Join-Path $RepositoryRoot "build\ffmpeg-input"
$ToolsRoot = Join-Path $RepositoryRoot "packaging\windows\tools"

function Assert-Sha256 {
    param([string]$Path, [string]$Expected)
    $Actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
    if ($Actual -ne $Expected) {
        throw "SHA-256 mismatch for $Path. Expected $Expected, got $Actual."
    }
}

function Get-PinnedFile {
    param([string]$Url, [string]$Path, [string]$Sha256)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        Write-Host "Downloading $Url"
        Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $Path
    }
    Assert-Sha256 $Path $Sha256
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

New-Item -ItemType Directory -Force -Path $CacheRoot,$ToolsRoot | Out-Null
if (-not $ArchivePath) {
    $ArchiveName = [System.IO.Path]::GetFileName(([uri]$Manifest.ffmpeg_archive_url).AbsolutePath)
    $ArchivePath = Join-Path $CacheRoot $ArchiveName
    Get-PinnedFile $Manifest.ffmpeg_archive_url $ArchivePath $Manifest.ffmpeg_archive_sha256
} else {
    $ArchivePath = (Resolve-Path -LiteralPath $ArchivePath).Path
    Assert-Sha256 $ArchivePath $Manifest.ffmpeg_archive_sha256
}

$StageRoot = Join-Path $RepositoryRoot ("build\ffmpeg-stage-" + [guid]::NewGuid().ToString("N"))
try {
    New-Item -ItemType Directory -Path $StageRoot | Out-Null
    Expand-Archive -LiteralPath $ArchivePath -DestinationPath $StageRoot
    $PackageRoots = @(Get-ChildItem -LiteralPath $StageRoot -Directory)
    if ($PackageRoots.Count -ne 1) {
        throw "Pinned FFmpeg archive must contain exactly one top-level directory."
    }
    $BinRoot = Join-Path $PackageRoots[0].FullName "bin"
    foreach ($Name in @("ffmpeg.exe", "ffprobe.exe")) {
        $Source = Join-Path $BinRoot $Name
        if (-not (Test-Path -LiteralPath $Source -PathType Leaf)) {
            throw "Pinned FFmpeg archive is missing bin/$Name."
        }
        Copy-Item -LiteralPath $Source -Destination (Join-Path $ToolsRoot $Name) -Force
    }
} finally {
    $ResolvedBuildRoot = (Resolve-Path -LiteralPath (Join-Path $RepositoryRoot "build")).Path
    $ResolvedStage = [System.IO.Path]::GetFullPath($StageRoot)
    if ($ResolvedStage.StartsWith($ResolvedBuildRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
        Remove-Item -LiteralPath $ResolvedStage -Recurse -Force -ErrorAction SilentlyContinue
    }
}

$LicenseInputs = @(
    [pscustomobject]@{
        Url = $Manifest.ffmpeg_gpl_license_url
        Name = "COPYING.GPLv3"
        Sha256 = $Manifest.ffmpeg_gpl_license_sha256
    },
    [pscustomobject]@{
        Url = $Manifest.ffmpeg_lgpl_license_url
        Name = "COPYING.LGPLv3"
        Sha256 = $Manifest.ffmpeg_lgpl_license_sha256
    }
)
foreach ($Input in $LicenseInputs) {
    Get-PinnedFile $Input.Url (Join-Path $ToolsRoot $Input.Name) $Input.Sha256
}

$FFmpegPath = Join-Path $ToolsRoot "ffmpeg.exe"
$FFprobePath = Join-Path $ToolsRoot "ffprobe.exe"
Assert-Sha256 $FFmpegPath $Manifest.ffmpeg_sha256
Assert-Sha256 $FFprobePath $Manifest.ffprobe_sha256
$Version = (& $FFmpegPath -version | Select-Object -First 1)
if ($Version -notlike "ffmpeg version $($Manifest.ffmpeg_version)*") {
    throw "ffmpeg.exe version does not match release/manifest.json: $Version"
}
$BuildConf = Get-BuildConfiguration $FFmpegPath
foreach ($Forbidden in @("--enable-gpl", "--enable-nonfree", "--enable-libx264", "--enable-libx265")) {
    if ($BuildConf.Contains($Forbidden)) {
        throw "Pinned FFmpeg configuration unexpectedly contains $Forbidden."
    }
}
foreach ($Required in @("--enable-version3", "--enable-libopenh264")) {
    if (-not $BuildConf.Contains($Required)) {
        throw "Pinned FFmpeg configuration is missing $Required."
    }
}

$SmokeOutput = Join-Path $CacheRoot ("openh264-smoke-" + [guid]::NewGuid().ToString("N") + ".mp4")
try {
    & $FFmpegPath -nostdin -hide_banner -loglevel error -y `
        -f lavfi -i "testsrc2=size=640x360:rate=25:duration=1" `
        -c:v $Manifest.ffmpeg_h264_encoder -b:v 2M -pix_fmt yuv420p -an `
        -movflags +faststart $SmokeOutput
    if ($LASTEXITCODE -ne 0) {
        throw "Pinned FFmpeg failed the synthetic H.264 encoder smoke test."
    }
    $ProbeJson = (& $FFprobePath -v error -select_streams v:0 `
        -show_entries stream=codec_name,pix_fmt,width,height -of json $SmokeOutput) -join "`n"
    if ($LASTEXITCODE -ne 0) {
        throw "Pinned FFprobe failed the synthetic H.264 encoder smoke test."
    }
    $Probe = $ProbeJson | ConvertFrom-Json
    $Video = @($Probe.streams)[0]
    if ($Video.codec_name -ne "h264" -or $Video.pix_fmt -ne "yuv420p" -or $Video.width -ne 640 -or $Video.height -ne 360) {
        throw "Pinned FFmpeg produced an unexpected H.264 smoke-test stream."
    }
} finally {
    Remove-Item -LiteralPath $SmokeOutput -Force -ErrorAction SilentlyContinue
}

if ($IncludeSourceSnapshots) {
    $SourceRoot = Join-Path $RepositoryRoot "release\output\source"
    New-Item -ItemType Directory -Force -Path $SourceRoot | Out-Null
    Get-PinnedFile $Manifest.ffmpeg_source_url (Join-Path $SourceRoot "ffmpeg-$($Manifest.ffmpeg_source_commit).tar.gz") $Manifest.ffmpeg_source_sha256
    Get-PinnedFile $Manifest.ffmpeg_build_source_url (Join-Path $SourceRoot "ffmpeg-builds-$($Manifest.ffmpeg_build_source_commit).tar.gz") $Manifest.ffmpeg_build_source_sha256
}

Write-Host "Pinned FFmpeg/FFprobe tools and license texts verified under packaging/windows/tools."
