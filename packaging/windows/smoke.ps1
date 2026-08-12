param(
    [string]$Executable = "artifacts\package\TraceCue\TraceCue.exe",
    [int]$Port = 8765
)

$ErrorActionPreference = "Stop"
$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$ResolvedExecutable = (Resolve-Path (Join-Path $RepositoryRoot $Executable)).Path
$SmokeRoot = Join-Path ([System.IO.Path]::GetTempPath()) "TraceCueSmoke-$PID"
$ResolvedTemp = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$ResolvedSmoke = [System.IO.Path]::GetFullPath($SmokeRoot)
if (-not $ResolvedSmoke.StartsWith($ResolvedTemp, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to use a smoke-test directory outside the system temporary directory."
}
New-Item -ItemType Directory -Path $ResolvedSmoke -Force | Out-Null

$env:TRACECUE_DATA_DIR = Join-Path $ResolvedSmoke "data"
$env:TRACECUE_CLIP_DIR = Join-Path $ResolvedSmoke "clips"
$env:TRACECUE_OPEN_BROWSER = "0"
$Process = Start-Process -FilePath $ResolvedExecutable -WindowStyle Hidden -PassThru
try {
    $Status = $null
    for ($Attempt = 0; $Attempt -lt 60; $Attempt++) {
        try {
            $Status = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/v1/status" -TimeoutSec 1
            break
        }
        catch {
            Start-Sleep -Milliseconds 500
        }
    }
    if ($null -eq $Status) {
        throw "Packaged TraceCue did not become ready on loopback."
    }
    if ($Status.bind_host -ne "127.0.0.1" -or $Status.schema_version -lt 1) {
        throw "Packaged TraceCue returned an unsafe or incomplete status response."
    }
    if (-not (Test-Path -LiteralPath (Join-Path $env:TRACECUE_DATA_DIR "tracecue.sqlite"))) {
        throw "Packaged TraceCue did not initialize its data store."
    }
    Write-Host "Installed application smoke test passed."
}
finally {
    if (-not $Process.HasExited) {
        Stop-Process -Id $Process.Id -Force
        $Process.WaitForExit(5000)
    }
    if (Test-Path -LiteralPath $ResolvedSmoke) {
        Remove-Item -LiteralPath $ResolvedSmoke -Recurse -Force
    }
}

