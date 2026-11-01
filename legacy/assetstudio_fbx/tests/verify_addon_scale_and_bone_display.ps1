$ErrorActionPreference = 'Stop'

$script = Join-Path $env:TEMP 'verify_addon_scale_and_bone_display.py'
$sourceInput = $env:UNITY3D_TEST_SOURCE
if (-not $sourceInput) {
  throw 'Set UNITY3D_TEST_SOURCE to a test Unity3D file before running this test.'
}
$blenderExe = $env:UNITY3D_BLENDER_EXE
if (-not $blenderExe) {
  throw 'Set UNITY3D_BLENDER_EXE to the Blender executable before running this test.'
}
$asciiInput = Join-Path (Get-Location) 'tests\_unity3d_scale_test_input.unity3d'
try {
  if (Test-Path -LiteralPath $asciiInput) {
    Remove-Item -LiteralPath $asciiInput -Force
  }
  Copy-Item -LiteralPath $sourceInput -Destination $asciiInput -Force
  $env:UNITY3D_TEST_INPUT = $asciiInput
  $env:UNITY3D_ADDON_ROOT = Join-Path (Get-Location) 'blender_addon'
  @'
import bpy
import os
import sys

addon_root = os.environ["UNITY3D_ADDON_ROOT"]
sys.path.insert(0, addon_root)
import unity3d_assetbundle_importer as addon

input_path = os.environ["UNITY3D_TEST_INPUT"]
root_name = os.path.splitext(os.path.basename(input_path))[0]

addon.register()
properties = bpy.ops.import_scene.unity3d_assetbundle.get_rna_type().properties
scale_property = properties["scale_factor"]
bone_property = properties["bone_display_type"]
cleanup_property = properties["cleanup_empty_hierarchy"]
property_ids = [item.identifier for item in properties]
print(f"SCALE_PROPERTY_TYPE={scale_property.type}")
print(f"SCALE_DEFAULT={scale_property.default}")
print(f"BONE_ITEMS={[item.name for item in bone_property.enum_items]}")
if scale_property.type != "FLOAT" or scale_property.default != 10.0:
    raise SystemExit("SCALE_PROPERTY_NOT_CONFIGURED")
if property_ids.index("scale_factor") >= property_ids.index("bone_display_type"):
    raise SystemExit("IMPORT_OPTION_ORDER_NOT_CONFIGURED")
if scale_property.is_hidden or bone_property.is_hidden or cleanup_property.is_hidden:
    raise SystemExit("IMPORT_OPTIONS_HIDDEN")
if cleanup_property.type != "BOOLEAN" or cleanup_property.default is not True:
    raise SystemExit("CLEANUP_PROPERTY_NOT_CONFIGURED")
if [item.name for item in bone_property.enum_items] != ["\u516b\u9762\u9525", "\u68cd\u5f62", "\u67d4\u6027\u9aa8\u9abc", "\u5c01\u5957", "\u7ebf\u6846"]:
    raise SystemExit("BONE_DISPLAY_ITEMS_NOT_CONFIGURED")
default_result = bpy.ops.import_scene.unity3d_assetbundle(
    filepath=input_path,
    output_dir="",
    clear_scene=True,
)
default_root = bpy.data.objects.get(root_name)
print(f"DEFAULT_OPERATOR_RESULT={default_result}")
print(f"DEFAULT_ROOT_SCALE={tuple(default_root.scale) if default_root else None}")
if default_result != {"FINISHED"}:
    raise SystemExit("DEFAULT_IMPORT_FAILED")
if default_root is None or tuple(default_root.scale) != (10.0, 10.0, 10.0):
    raise SystemExit("DEFAULT_SCALE_FACTOR_NOT_APPLIED")
if any(obj.type == "EMPTY" and obj.parent and obj.parent.type == "EMPTY" for obj in default_root.children_recursive):
    raise SystemExit("DEFAULT_EMPTY_HIERARCHY_NOT_CLEANED")
preserve_result = bpy.ops.import_scene.unity3d_assetbundle(
    filepath=input_path,
    output_dir="",
    clear_scene=True,
    cleanup_empty_hierarchy=False,
)
preserve_root = bpy.data.objects.get(root_name)
print(f"PRESERVE_OPERATOR_RESULT={preserve_result}")
if preserve_result != {"FINISHED"} or preserve_root is None:
    raise SystemExit("PRESERVE_IMPORT_FAILED")
if not any(obj.type == "EMPTY" and obj.parent and obj.parent.type == "EMPTY" for obj in preserve_root.children_recursive):
    raise SystemExit("PRESERVE_EMPTY_HIERARCHY_NOT_RETAINED")
result = bpy.ops.import_scene.unity3d_assetbundle(
    filepath=input_path,
    output_dir="",
    clear_scene=True,
    scale_factor=3.5,
    bone_display_type="ENVELOPE",
    cleanup_empty_hierarchy=True,
)
print(f"OPERATOR_RESULT={result}")

root = bpy.data.objects.get(root_name)
armatures = [obj for obj in root.children_recursive if obj.type == "ARMATURE"] if root else []
print(f"ROOT_SCALE={tuple(root.scale) if root else None}")
print(f"ARMATURE_DISPLAY={[obj.data.display_type for obj in armatures]}")

if result != {"FINISHED"}:
    raise SystemExit("IMPORT_FAILED")
if root is None or tuple(root.scale) != (3.5, 3.5, 3.5):
    raise SystemExit("SCALE_FACTOR_NOT_APPLIED")
if not armatures:
    raise SystemExit("NO_ARMATURE_IMPORTED")
if any(obj.data.display_type != "ENVELOPE" for obj in armatures):
    raise SystemExit("BONE_DISPLAY_MODE_NOT_APPLIED")
if any(obj.type == "EMPTY" and obj.parent and obj.parent.type == "EMPTY" for obj in root.children_recursive):
    raise SystemExit("CUSTOM_EMPTY_HIERARCHY_NOT_CLEANED")
'@ | Set-Content -LiteralPath $script -Encoding UTF8

  & $blenderExe --background --factory-startup --python $script
}
finally {
  Remove-Item -LiteralPath $asciiInput -Force -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath $script -Force -ErrorAction SilentlyContinue
}
