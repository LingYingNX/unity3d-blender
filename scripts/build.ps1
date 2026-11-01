$ErrorActionPreference = 'Stop'

$repo = Split-Path -Parent $PSScriptRoot
$assetStudio = Join-Path $repo 'third_party\AssetStudio'
$project = Join-Path $repo 'src\AssetBundleToBlender\AssetBundleToBlender.csproj'
$output = Join-Path $repo 'legacy\assetstudio_fbx\tools\AssetBundleToBlender'

if (!(Test-Path -Path $assetStudio)) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $assetStudio) | Out-Null
    git clone https://github.com/Perfare/AssetStudio.git $assetStudio
}

dotnet publish $project -c Release -r win-x64 --self-contained false -o $output
