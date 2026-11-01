$ErrorActionPreference = 'Stop'

$script = Join-Path $env:TEMP 'verify_cleanup_empty_hierarchy.py'
$blenderExe = $env:UNITY3D_BLENDER_EXE
if (-not $blenderExe) {
  throw 'Set UNITY3D_BLENDER_EXE to the Blender executable before running this test.'
}
$addonRoot = Join-Path (Get-Location) 'blender_addon'

try {
  @'
import bpy
import os
import sys

sys.path.insert(0, os.environ["UNITY3D_ADDON_ROOT"])
import unity3d_assetbundle_importer as addon

addon.register()
collection = bpy.context.scene.collection
root = bpy.data.objects.new("cleanup_test_root", None)
collection.objects.link(root)

levels = []
parent = root
for index in range(5):
    empty = bpy.data.objects.new(f"cleanup_test_empty_{index}", None)
    collection.objects.link(empty)
    empty.parent = parent
    empty.location = (index + 1, index * 0.5, 0.0)
    levels.append(empty)
    parent = empty

mesh_data = bpy.data.meshes.new("cleanup_test_mesh_data")
mesh = bpy.data.objects.new("cleanup_test_mesh", mesh_data)
collection.objects.link(mesh)
mesh.parent = levels[-1]
mesh.location = (2.0, 3.0, 4.0)
mesh.rotation_euler[2] = 0.25

armature_data = bpy.data.armatures.new("cleanup_test_armature_data")
armature = bpy.data.objects.new("cleanup_test_armature", armature_data)
collection.objects.link(armature)
armature.parent = levels[-2]
armature.location = (-1.0, 2.0, 0.5)

protected = bpy.data.objects.new("cleanup_test_protected", None)
collection.objects.link(protected)
protected.parent = root
protected["keep_marker"] = True
protected_mesh_data = bpy.data.meshes.new("cleanup_test_protected_mesh_data")
protected_mesh = bpy.data.objects.new("cleanup_test_protected_mesh", protected_mesh_data)
collection.objects.link(protected_mesh)
protected_mesh.parent = protected

mesh_world_before = mesh.matrix_world.copy()
armature_world_before = armature.matrix_world.copy()
addon._flatten_empty_hierarchy(root, [*levels, mesh, armature, protected, protected_mesh])

def matrix_changed(before, after):
    return any(abs(before[row][column] - after[row][column]) > 0.0001 for row in range(4) for column in range(4))

empty_descendants = [obj for obj in root.children_recursive if obj.type == "EMPTY"]
print(f"EMPTY_DESCENDANT_COUNT={len(empty_descendants)}")
print(f"MESH_PARENT={mesh.parent.name if mesh.parent else None}")
print(f"ARMATURE_PARENT={armature.parent.name if armature.parent else None}")
print(f"PROTECTED_PARENT={protected.parent.name if protected.parent else None}")

if root.type != "EMPTY":
    raise SystemExit("ROOT_EMPTY_REMOVED")
if empty_descendants != [protected]:
    raise SystemExit("STRUCTURAL_EMPTY_NOT_FLATTENED")
if mesh.parent is not root or armature.parent is not root:
    raise SystemExit("DATA_OBJECTS_NOT_REPARENTED_TO_ROOT")
if protected.parent is not root or protected_mesh.parent is not protected:
    raise SystemExit("PROTECTED_EMPTY_NOT_PRESERVED")
if matrix_changed(mesh_world_before, mesh.matrix_world):
    raise SystemExit("MESH_WORLD_TRANSFORM_CHANGED")
if matrix_changed(armature_world_before, armature.matrix_world):
    raise SystemExit("ARMATURE_WORLD_TRANSFORM_CHANGED")
'@ | Set-Content -LiteralPath $script -Encoding UTF8
  $env:UNITY3D_ADDON_ROOT = $addonRoot
  & $blenderExe --background --factory-startup --python $script
}
finally {
  Remove-Item -LiteralPath $script -Force -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath (Join-Path $addonRoot 'unity3d_assetbundle_importer\__pycache__') -Recurse -Force -ErrorAction SilentlyContinue
}
