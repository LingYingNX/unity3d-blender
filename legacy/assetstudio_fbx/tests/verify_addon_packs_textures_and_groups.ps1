$ErrorActionPreference = 'Stop'

$script = Join-Path $env:TEMP 'verify_addon_packs_textures_and_groups.py'
$sourceInput = 'C:\Users\LYNX\Desktop\[sakuraba]哥谭蝴蝶梦\abdata\chara\sakuraba\sakuraba_25-5-s01.unity3d'
$asciiInput = Join-Path $env:TEMP 'sakuraba_25-5-s01.unity3d'
Copy-Item -LiteralPath $sourceInput -Destination $asciiInput -Force
$env:UNITY3D_TEST_INPUT = $asciiInput
$env:UNITY3D_TEST_FORBIDDEN_OUTPUT = Join-Path $env:TEMP 'sakuraba_25-5-s01_fbx_export'
@'
import addon_utils
import bpy
import os

addon_name = "unity3d_assetbundle_importer"
input_path = os.environ["UNITY3D_TEST_INPUT"]
forbidden_output = os.environ["UNITY3D_TEST_FORBIDDEN_OUTPUT"]

addon_utils.enable(addon_name, default_set=False, persistent=False)
if not hasattr(bpy.ops.import_scene, "unity3d_assetbundle"):
    raise SystemExit("OPERATOR_NOT_REGISTERED")

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete()
result = bpy.ops.import_scene.unity3d_assetbundle(filepath=input_path, output_dir="", clear_scene=True)
print(f"OPERATOR_RESULT={result}")

images = list(bpy.data.images)
packed_images = [image for image in images if image.packed_file is not None]
unpacked_missing_images = []
for image in images:
    if image.packed_file is not None or not image.filepath:
        continue
    image_path = bpy.path.abspath(image.filepath)
    if image_path and not os.path.exists(image_path):
        unpacked_missing_images.append(image_path)

root_name = os.path.splitext(os.path.basename(input_path))[0]
root = bpy.data.objects.get(root_name)
scene_roots = [obj for obj in bpy.context.scene.objects if obj.parent is None]
children = list(root.children) if root else []

print(f"IMAGE_COUNT={len(images)}")
print(f"PACKED_IMAGE_COUNT={len(packed_images)}")
print(f"UNPACKED_MISSING_IMAGE_COUNT={len(unpacked_missing_images)}")
print(f"CHARACTER_ROOT_EXISTS={root is not None}")
print(f"CHARACTER_ROOT_TYPE={root.type if root else ''}")
print(f"SCENE_ROOT_COUNT={len(scene_roots)}")
print(f"CHARACTER_ROOT_CHILDREN={len(children)}")
print(f"FORBIDDEN_OUTPUT_EXISTS={os.path.exists(forbidden_output)}")

if not images:
    raise SystemExit("NO_IMAGES_IMPORTED")
if not packed_images:
    raise SystemExit("TEXTURES_NOT_PACKED")
if unpacked_missing_images:
    raise SystemExit("UNPACKED_MISSING_TEXTURES")
if root is None or root.type != "EMPTY":
    raise SystemExit("CHARACTER_ROOT_NOT_CREATED")
if len(children) < 7:
    raise SystemExit("IMPORTED_PARTS_NOT_GROUPED_UNDER_CHARACTER_ROOT")
if any(obj is not root for obj in scene_roots):
    raise SystemExit("IMPORTED_OBJECTS_LEFT_AT_SCENE_ROOT")
if os.path.exists(forbidden_output):
    raise SystemExit("SOURCE_DIRECTORY_OUTPUT_CREATED")
'@ | Set-Content -LiteralPath $script -Encoding UTF8

& 'E:\blender\blender-5.0.1-windows-x64\blender.exe' --background --factory-startup --python $script
