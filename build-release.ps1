$ErrorActionPreference = "Stop"

$base = Split-Path -Parent $MyInvocation.MyCommand.Path
$releaseDir = Join-Path $base "release"
$stage = Join-Path $releaseDir "NanoKVM-Mirror-v1.0.0"
$zip = Join-Path $releaseDir "NanoKVM-Mirror-v1.0.0.zip"

if (Test-Path $stage) {
    Remove-Item $stage -Recurse -Force
}

New-Item -ItemType Directory -Path $stage -Force | Out-Null

$files = @(
    "NanoKVM-Mirror.exe",
    "kvm-screen-mirror.py",
    "mirror-kvm-screen.cmd",
    "mirror-kvm-screen.vbs",
    "README.md",
    "RELEASE_NOTES.md",
    "gif.gif",
    "kvm-screen-mirror.example.json"
)

foreach ($file in $files) {
    Copy-Item -Path (Join-Path $base $file) -Destination (Join-Path $stage $file) -Force
}

if (Test-Path $zip) {
    Remove-Item $zip -Force
}

Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zip -Force

$hash = (Get-FileHash -Algorithm SHA256 $zip).Hash
Set-Content -Path (Join-Path $releaseDir "SHA256SUMS.txt") -Value "$hash  NanoKVM-Mirror-v1.0.0.zip"

Write-Output $zip
Write-Output $hash
