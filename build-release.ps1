$ErrorActionPreference = "Stop"

$base = Split-Path -Parent $MyInvocation.MyCommand.Path
$version = "v2.0.0"
$releaseDir = Join-Path $base "release"
$distExe = Join-Path $base "dist\\NanoKVM-Mirror.exe"
$stage = Join-Path $releaseDir "NanoKVM-Mirror-$version"
$zip = Join-Path $releaseDir "NanoKVM-Mirror-$version.zip"

if (Test-Path $stage) {
    Remove-Item $stage -Recurse -Force
}

New-Item -ItemType Directory -Path $stage -Force | Out-Null

if (-not (Test-Path $distExe)) {
    throw "Build artifact not found: $distExe"
}

$files = @(
    "kvm-screen-mirror.py",
    "mirror-kvm-screen.cmd",
    "mirror-kvm-screen.vbs",
    "README.md",
    "RELEASE_NOTES.md",
    "gif.gif",
    "kvm-screen-mirror.example.json"
)

Copy-Item -Path $distExe -Destination (Join-Path $stage "NanoKVM-Mirror.exe") -Force

foreach ($file in $files) {
    Copy-Item -Path (Join-Path $base $file) -Destination (Join-Path $stage $file) -Force
}

if (Test-Path $zip) {
    Remove-Item $zip -Force
}

Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zip -Force

$hash = (Get-FileHash -Algorithm SHA256 $zip).Hash
Set-Content -Path (Join-Path $releaseDir "SHA256SUMS.txt") -Value "$hash  NanoKVM-Mirror-$version.zip"

Write-Output $zip
Write-Output $hash
