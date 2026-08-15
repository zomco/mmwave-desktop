$ErrorActionPreference = "Stop"
$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Manifest = Get-Content -Raw -Encoding utf8 (Join-Path $RepositoryRoot "release\manifest.json") | ConvertFrom-Json
$ModelRoot = Join-Path $RepositoryRoot "packaging\windows\models"
$ModelPath = Join-Path $ModelRoot "yolox_nano.onnx"
$LicensePath = Join-Path $ModelRoot "LICENSE.YOLOX"

function Get-PinnedFile {
    param([string]$Url, [string]$Path, [string]$Sha256)
    if (Test-Path -LiteralPath $Path -PathType Leaf) {
        $Actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
        if ($Actual -ne $Sha256) {
            throw "SHA-256 mismatch for existing $Path. Expected $Sha256, got $Actual."
        }
        return
    }
    $PartialPath = "$Path.partial"
    try {
        Write-Host "Downloading $Url"
        Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $PartialPath
        $Actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $PartialPath).Hash.ToLowerInvariant()
        if ($Actual -ne $Sha256) {
            throw "SHA-256 mismatch for $Url. Expected $Sha256, got $Actual."
        }
        Move-Item -LiteralPath $PartialPath -Destination $Path
    }
    finally {
        Remove-Item -LiteralPath $PartialPath -Force -ErrorAction SilentlyContinue
    }
}

New-Item -ItemType Directory -Force -Path $ModelRoot | Out-Null
Get-PinnedFile $Manifest.vision_model_url $ModelPath $Manifest.vision_model_sha256
Get-PinnedFile $Manifest.vision_model_license_url $LicensePath $Manifest.vision_model_license_sha256
Write-Host "Pinned optional YOLOX-Nano model and Apache-2.0 license verified under packaging/windows/models."
