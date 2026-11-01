$ErrorActionPreference = 'Stop'

$repo = Split-Path -Parent $PSScriptRoot
$addon = Join-Path $repo 'blender_addon\unity3d_assetbundle_importer'
$dist = Join-Path $repo 'dist'
$zip = Join-Path $dist 'unity3d_assetbundle_importer_blender_addon.zip'
$stage = Join-Path $dist 'zip_stage'

if (Test-Path -Path $stage) {
    Remove-Item -Path $stage -Recurse -Force
}

New-Item -ItemType Directory -Force -Path $stage | Out-Null
New-Item -ItemType Directory -Force -Path $dist | Out-Null
Copy-Item -Path $addon -Destination $stage -Recurse -Force

if (Test-Path -Path $zip) {
    Remove-Item -Path $zip -Force
}

Compress-Archive -Path (Join-Path $stage 'unity3d_assetbundle_importer') -DestinationPath $zip -Force
Remove-Item -Path $stage -Recurse -Force

Write-Host "Wrote $zip"
