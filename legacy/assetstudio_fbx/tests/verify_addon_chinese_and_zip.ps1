$ErrorActionPreference = 'Stop'
$source = 'E:\BaiduSyncdisk\codex目录\其它\.codex\tools\AssetBundleToBlender\blender_addon\unity3d_assetbundle_importer\__init__.py'
$installed = 'E:\blender\blender-5.0.1-windows-x64\portable\scripts\addons\unity3d_assetbundle_importer\__init__.py'
$zip = 'C:\Users\LYNX\Desktop\Unity3D资源包导入器_Blender插件.zip'
$required = @(
  '"name": "Unity3D资源包导入器"',
  '"description": "选择 Unity3D AssetBundle 文件，临时转换为 FBX，打包贴图并导入当前 Blender 场景。"',
  '"location": "文件 > 导入 > Unity3D资源包 (.unity3d)"',
  'bl_label = "导入 Unity3D 资源包"',
  'text="Unity3D资源包 (.unity3d)"'
)
foreach ($path in @($source, $installed)) {
  $text = Get-Content -LiteralPath $path -Raw -Encoding UTF8
  foreach ($needle in $required) {
    if (-not $text.Contains($needle)) {
      Write-Host "RED: missing Chinese addon metadata [$needle] in $path"
      exit 1
    }
  }
}
if (-not (Test-Path -LiteralPath $zip)) {
  Write-Host "RED: desktop addon zip does not exist: $zip"
  exit 1
}
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [System.IO.Compression.ZipFile]::OpenRead($zip)
try {
  $entries = $archive.Entries | ForEach-Object { $_.FullName }
  if (-not ($entries -contains 'unity3d_assetbundle_importer/__init__.py')) {
    Write-Host 'RED: zip is not a Blender-installable addon folder archive'
    exit 1
  }
}
finally {
  $archive.Dispose()
}
Write-Host 'GREEN: addon metadata is Chinese and desktop zip is installable'
