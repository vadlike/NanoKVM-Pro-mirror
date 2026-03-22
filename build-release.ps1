$ErrorActionPreference = "Stop"

$base = Split-Path -Parent $MyInvocation.MyCommand.Path
$releaseDir = Join-Path $base "release"
$distExe = Join-Path $base "dist\\NanoKVM-Mirror.exe"

if (-not (Test-Path $distExe)) {
    throw "Build artifact not found: $distExe"
}

if (Test-Path $releaseDir) {
    Remove-Item $releaseDir -Recurse -Force
}

New-Item -ItemType Directory -Path $releaseDir -Force | Out-Null

$releaseExe = Join-Path $releaseDir "NanoKVM-Mirror.exe"
Copy-Item -Path $distExe -Destination $releaseExe -Force
Write-Output $releaseExe
