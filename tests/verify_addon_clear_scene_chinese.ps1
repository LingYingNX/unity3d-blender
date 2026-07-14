$ErrorActionPreference = 'Stop'

$blenderExe = $env:UNITY3D_BLENDER_EXE
if (-not $blenderExe) {
  throw 'Set UNITY3D_BLENDER_EXE to the Blender executable before running this test.'
}

$env:UNITY3D_ADDON_ROOT = Join-Path (Get-Location) 'blender_addon'
$scriptPath = Join-Path $env:TEMP 'verify_addon_clear_scene_chinese.py'
try {
@'
import bpy
import os
import sys

addon_root = os.environ["UNITY3D_ADDON_ROOT"]
sys.path.insert(0, addon_root)
import unity3d_assetbundle_importer as addon

addon.register()
try:
    property_info = bpy.ops.import_scene.unity3d_assetbundle.get_rna_type().properties["clear_scene"]
    print(f"CLEAR_SCENE_NAME={property_info.name}")
    print(f"CLEAR_SCENE_DESCRIPTION={property_info.description}")
    if property_info.name != "\u5bfc\u5165\u524d\u6e05\u7406\u573a\u666f":
        raise SystemExit("CLEAR_SCENE_NAME_NOT_CHINESE")
    if property_info.description != "\u5bfc\u5165 FBX \u524d\u5220\u9664\u73b0\u6709\u573a\u666f\u5bf9\u8c61":
        raise SystemExit("CLEAR_SCENE_DESCRIPTION_NOT_CHINESE")
finally:
    addon.unregister()
'@ | Set-Content -LiteralPath $scriptPath -Encoding utf8

  & $blenderExe --factory-startup --background --python $scriptPath
  if ($LASTEXITCODE -ne 0) {
    throw "Blender RNA localization check failed with exit code $LASTEXITCODE."
  }
  Write-Host 'GREEN: clear_scene RNA metadata is Chinese'
}
finally {
  Remove-Item -LiteralPath $scriptPath -Force -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath (Join-Path $env:UNITY3D_ADDON_ROOT 'unity3d_assetbundle_importer\__pycache__') -Recurse -Force -ErrorAction SilentlyContinue
}
