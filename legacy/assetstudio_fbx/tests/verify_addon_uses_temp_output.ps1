$ErrorActionPreference = 'Stop'
$source = 'E:\BaiduSyncdisk\codex目录\其它\.codex\tools\AssetBundleToBlender\blender_addon\unity3d_assetbundle_importer\__init__.py'
$installed = 'E:\blender\blender-5.0.1-windows-x64\portable\scripts\addons\unity3d_assetbundle_importer\__init__.py'
foreach ($path in @($source, $installed)) {
  $text = Get-Content -LiteralPath $path -Raw
  if ($text -notmatch 'tempfile\.TemporaryDirectory') {
    Write-Host "RED: plugin does not use a temporary conversion directory: $path"
    exit 1
  }
  if ($text -match 'input_path\.with_name\(input_path\.stem \+ "_fbx_export"\)') {
    Write-Host "RED: plugin still defaults to exporting beside the source unity3d file: $path"
    exit 1
  }
}
Write-Host 'GREEN: plugin uses temporary conversion output and avoids source-directory extraction'
